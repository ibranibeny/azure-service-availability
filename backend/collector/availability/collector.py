"""Scheduled collection of Azure service availability.

Data sources (all called through the Azure CLI):
  az account list-locations           regions, geography, coordinates, zone mappings
  az provider list                    resource type locations + zone mappings per service
  az rest  .../Microsoft.Compute/skus VM SKU availability and restrictions per region
                                      (same Resource SKUs API that `az vm list-skus` uses,
                                      called with the server-side location filter)
  az rest  .../Microsoft.Web/geoRegions?sku=FlexConsumption   Functions Flex regions
  az rest  https://prices.azure.com/api/retail/prices         Azure Managed Redis SKUs
                                      with a pay-as-you-go meter in each region
The snapshot is written to Azure Managed Redis (Microsoft Entra auth, no access keys).
"""
import concurrent.futures as cf
import datetime as dt
import json
import logging
import os
import time

from .azcli import AzCli, AzError
from . import catalog, store

LOG = logging.getLogger("availability.collector")

VM_CAPS = ["vCPUs", "MemoryGB", "GPUs", "CpuArchitectureType", "HyperVGenerations", "PremiumIO",
           "AcceleratedNetworkingEnabled", "LowPriorityCapable", "EncryptionAtHostSupported",
           "EphemeralOSDiskSupported", "MaxDataDiskCount", "MaxNetworkInterfaces", "UltraSSDAvailable",
           "TrustedLaunchDisabled", "ConfidentialComputingType", "RetirementDateUtc", "LifecycleState"]
VM_QUERY = ("value[?resourceType=='virtualMachines'].{n:name,f:family,s:size,t:tier,"
            "z:locationInfo[0].zones,r:restrictions[].{t:type,c:reasonCode,z:restrictionInfo.zones},"
            "c:capabilities[?contains(`%s`, name)]}" % json.dumps(VM_CAPS, separators=(",", ":")))
VM_COLUMNS = ["name", "family", "size", "vcpus", "memoryGB", "gpus", "arch", "hyperV", "premiumIO",
              "accelNet", "spot", "encryptionAtHost", "ephemeralOS", "maxDataDisks", "maxNics",
              "ultraSSD", "trustedLaunch", "confidential", "zones", "zonesRestricted", "status",
              "reason", "retirement", "lifecycle"]
PRICE_FILTER = ("serviceName eq 'Redis Cache' and priceType eq 'Consumption' "
                "and contains(productName, 'Azure Managed Redis')")


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _b(v):
    return str(v).lower() == "true"


def _num(v, cast=float):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return None


def collect_regions(az):
    rows = az.run("account", "list-locations", "--query",
                  "[?metadata.regionType=='Physical'].{name:name,displayName:displayName,"
                  "regional:regionalDisplayName,m:metadata,zones:availabilityZoneMappings}")
    regions = []
    for r in rows or []:
        m = r.get("m") or {}
        lat, lon = _num(m.get("latitude")), _num(m.get("longitude"))
        if lat is None or lon is None:
            continue
        regions.append({
            "name": r["name"],
            "displayName": r["displayName"],
            "geography": m.get("geography"),
            "geographyGroup": m.get("geographyGroup"),
            "physicalLocation": m.get("physicalLocation"),
            "category": m.get("regionCategory"),
            "lat": round(lat, 4), "lon": round(lon, 4),
            "paired": [p.get("name") for p in (m.get("pairedRegion") or []) if p.get("name")],
            "zones": len(r.get("zones") or []),
        })
    regions.sort(key=lambda x: (x["geographyGroup"] or "", x["displayName"]))
    return regions


def collect_providers(az):
    return az.run("provider", "list", "--query",
                  "[].{ns:namespace,types:resourceTypes[].{t:resourceType,l:locations,z:zoneMappings}}")


def collect_flex(az):
    data = az.run("rest", "--method", "get", "--url",
                  "/subscriptions/{subscriptionId}/providers/Microsoft.Web/geoRegions"
                  "?sku=FlexConsumption&api-version=2023-01-01")
    return [v.get("properties", {}).get("displayName") or v.get("name") for v in (data or {}).get("value", [])]


def collect_vm_region(az, region):
    rows = az.run("rest", "--method", "get", "--url",
                  "/subscriptions/{subscriptionId}/providers/Microsoft.Compute/skus",
                  "--uri-parameters", "api-version=2021-07-01", "$filter=location eq '%s'" % region,
                  "--query", VM_QUERY, timeout=300, retries=2)
    out = []
    for s in rows or []:
        caps = {c["name"]: c["value"] for c in (s.get("c") or [])}
        zones = sorted(s.get("z") or [])
        status, reason, zr = "available", "", set()
        for r in s.get("r") or []:
            if r.get("t") == "Location":
                status, reason = "restricted", r.get("c") or "Restricted"
            elif r.get("t") == "Zone":
                zr.update(r.get("z") or [])
        out.append([
            s["n"], s.get("f") or "", s.get("s") or "",
            _num(caps.get("vCPUs"), int), _num(caps.get("MemoryGB")), _num(caps.get("GPUs"), int) or 0,
            caps.get("CpuArchitectureType") or "", caps.get("HyperVGenerations") or "",
            _b(caps.get("PremiumIO")), _b(caps.get("AcceleratedNetworkingEnabled")),
            _b(caps.get("LowPriorityCapable")), _b(caps.get("EncryptionAtHostSupported")),
            _b(caps.get("EphemeralOSDiskSupported")), _num(caps.get("MaxDataDiskCount"), int),
            _num(caps.get("MaxNetworkInterfaces"), int), _b(caps.get("UltraSSDAvailable")),
            not _b(caps.get("TrustedLaunchDisabled")), caps.get("ConfidentialComputingType") or "",
            [z for z in zones if z not in zr], sorted(zr & set(zones)) if zones else sorted(zr),
            status, reason, (caps.get("RetirementDateUtc") or "")[:10], caps.get("LifecycleState") or "",
        ])
    out.sort(key=lambda x: (x[1], x[3] or 0, x[0]))
    return out


def collect_amr_prices(az):
    page = az.run("rest", "--method", "get", "--skip-authorization-header", "--url",
                  "https://prices.azure.com/api/retail/prices",
                  "--uri-parameters", json.dumps({"$filter": PRICE_FILTER}), retries=2)
    items = list(page.get("Items") or [])
    pages = 1
    nxt = page.get("NextPageLink")
    while nxt and pages < 25:
        page = az.run("rest", "--method", "get", "--skip-authorization-header", "--url", nxt, retries=2)
        items.extend(page.get("Items") or [])
        nxt = page.get("NextPageLink")
        pages += 1
    prices = {}
    for it in items:
        meter = it.get("meterName") or ""
        if not meter.endswith("Cache Instance"):
            continue
        region = (it.get("armRegionName") or "").lower()
        product = it.get("productName") or ""
        tier = product.split(" - ", 1)[1] if " - " in product else product
        sku = meter.split()[0]
        if not region or not sku:
            continue
        prices.setdefault(region, {})[sku] = {"tier": tier, "usdPerHour": it.get("unitPrice")}
    return prices, len(items), pages


def run(trigger="timer"):
    t0 = time.monotonic()
    started = utcnow()
    client_id = os.environ["AZURE_CLIENT_ID"]
    subscription = os.environ["AZURE_SUBSCRIPTION_ID"]
    parallel = int(os.environ.get("VM_PARALLELISM", "8"))
    errors = []

    az = AzCli()
    az.run("login", "--identity", "--client-id", client_id, "--allow-no-subscriptions", output="none")
    az.run("account", "set", "--subscription", subscription, output="none")
    cli_version = (az.run("version") or {}).get("azure-cli", "")
    # Entra token for Azure Managed Redis, issued to the Function's managed identity.
    token = az.run("account", "get-access-token", "--resource", "https://redis.azure.com",
                   "--query", "accessToken", output="tsv")
    db = store.Store(token)

    try:
        regions = collect_regions(az)
        by_display = {}
        for r in regions:
            by_display[norm(r["displayName"])] = r["name"]
            by_display[norm(r["name"])] = r["name"]
        names = [r["name"] for r in regions]

        def guarded(step, fn, default):
            try:
                return fn()
            except AzError as e:
                errors.append({"step": step, "error": str(e)[:400]})
                return default

        with cf.ThreadPoolExecutor(max_workers=3) as ex:
            f_prov = ex.submit(guarded, "az provider list", lambda: collect_providers(az), [])
            f_flex = ex.submit(guarded, "flex consumption regions", lambda: collect_flex(az), [])
            f_price = ex.submit(guarded, "retail prices", lambda: collect_amr_prices(az), ({}, 0, 0))
            providers, flex = f_prov.result(), f_flex.result()
            prices, price_items, price_pages = f_price.result()

        previous = {"summary": db.get_json("summary"), "vmindex": db.get_json("vmindex"),
                    "amr": db.get_json("amr")}

        vm = {}
        with cf.ThreadPoolExecutor(max_workers=parallel) as ex:
            futs = {ex.submit(collect_vm_region, az, n): n for n in names}
            for f in cf.as_completed(futs):
                n = futs[f]
                try:
                    vm[n] = {"rows": f.result(), "stale": False}
                except Exception as e:  # keep the last good data for this region
                    errors.append({"step": "vm skus " + n, "error": str(e)[:400]})
                    prev = db.get_json("region:" + n)
                    rows = ((prev or {}).get("vm") or {}).get("rows") or []
                    vm[n] = {"rows": rows, "stale": True}
        if not any(not v["stale"] for v in vm.values()):
            raise RuntimeError("VM SKU collection failed for every region; keeping the previous snapshot. "
                               "First error: %s" % (errors[0] if errors else "unknown"))

        services = catalog.service_availability(providers, flex, by_display)
        docs = catalog.build_documents(
            regions=regions, vm=vm, vm_columns=VM_COLUMNS, services=services, prices=prices,
            generated_at=started.isoformat().replace("+00:00", "Z"),
            meta={
                "schedule": os.environ.get("COLLECT_SCHEDULE", ""),
                "trigger": trigger,
                "azCliVersion": cli_version,
                "priceItems": price_items, "pricePages": price_pages,
                "errors": errors,
            })
        docs["changes"] = catalog.diff(previous, docs)
        duration = round(time.monotonic() - t0, 1)
        docs["summary"]["meta"]["durationSec"] = duration
        docs["summary"]["meta"]["azCalls"] = len(az.calls)
        record = {
            "at": docs["summary"]["generatedAt"], "trigger": trigger, "ok": True,
            "durationSec": duration, "regions": len(regions),
            "vmRows": sum(len(v["rows"]) for v in vm.values()),
            "azCalls": len(az.calls), "errors": len(errors),
            "slowest": sorted(az.calls, key=lambda c: -c["ms"])[:5],
        }
        db.write(docs, record)
        return {k: record[k] for k in ("at", "durationSec", "regions", "vmRows", "azCalls", "errors")}
    except Exception as e:
        db.add_run({"at": started.isoformat().replace("+00:00", "Z"), "trigger": trigger, "ok": False,
                    "durationSec": round(time.monotonic() - t0, 1), "error": str(e)[:500],
                    "azCalls": len(az.calls)})
        raise
    finally:
        az.cleanup()
