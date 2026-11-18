"""Service catalog and snapshot document builder."""
import re

# Services shown on the dashboard. Availability comes from `az provider list`
# (resource type locations + zone mappings), except Functions Flex Consumption,
# which comes from the Microsoft.Web geoRegions API (`az rest`).
SERVICES = [
    ("vm", "Virtual Machines", "Compute", "Microsoft.Compute", "virtualMachines", "virtual-machine"),
    ("vmss", "Virtual Machine Scale Sets", "Compute", "Microsoft.Compute", "virtualMachineScaleSets", "vm-scale-sets"),
    ("funcflex", "Functions (Flex Consumption)", "Compute", "Microsoft.Web", "geoRegions:FlexConsumption", "function-apps"),
    ("appsvc", "App Service", "Web", "Microsoft.Web", "sites", "app-services"),
    ("aks", "Azure Kubernetes Service", "Containers", "Microsoft.ContainerService", "managedClusters", "kubernetes-services"),
    ("aca", "Azure Container Apps", "Containers", "Microsoft.App", "managedEnvironments", "container-apps-environments"),
    ("acr", "Container Registry", "Containers", "Microsoft.ContainerRegistry", "registries", "container-registries"),
    ("amr", "Azure Managed Redis", "Databases", "Microsoft.Cache", "redisEnterprise", "azure-managed-redis"),
    ("redis", "Azure Cache for Redis", "Databases", "Microsoft.Cache", "Redis", "cache-redis"),
    ("cosmos", "Azure Cosmos DB", "Databases", "Microsoft.DocumentDB", "databaseAccounts", "azure-cosmos-db"),
    ("sqldb", "Azure SQL Database", "Databases", "Microsoft.Sql", "servers", "sql-database"),
    ("pg", "Azure Database for PostgreSQL", "Databases", "Microsoft.DBforPostgreSQL", "flexibleServers", "azure-database-postgresql-server"),
    ("mysql", "Azure Database for MySQL", "Databases", "Microsoft.DBforMySQL", "flexibleServers", "azure-database-mysql-server"),
    ("storage", "Storage accounts", "Storage", "Microsoft.Storage", "storageAccounts", "storage-accounts"),
    ("netapp", "Azure NetApp Files", "Storage", "Microsoft.NetApp", "netAppAccounts", "azure-netapp-files"),
    ("foundry", "Azure AI Foundry / OpenAI", "AI", "Microsoft.CognitiveServices", "accounts", "ai-foundry"),
    ("search", "Azure AI Search", "AI", "Microsoft.Search", "searchServices", "cognitive-search"),
    ("ml", "Azure Machine Learning", "AI", "Microsoft.MachineLearningServices", "workspaces", "machine-learning"),
    ("dbx", "Azure Databricks", "Analytics", "Microsoft.Databricks", "workspaces", "azure-databricks"),
    ("eh", "Event Hubs", "Integration", "Microsoft.EventHub", "namespaces", "event-hubs"),
    ("sb", "Service Bus", "Integration", "Microsoft.ServiceBus", "namespaces", "service-bus"),
    ("apim", "API Management", "Integration", "Microsoft.ApiManagement", "service", "api-management-services"),
    ("kv", "Key Vault", "Security", "Microsoft.KeyVault", "vaults", "key-vaults"),
    ("appgw", "Application Gateway", "Networking", "Microsoft.Network", "applicationGateways", "application-gateways"),
    ("fw", "Azure Firewall", "Networking", "Microsoft.Network", "azureFirewalls", "firewalls"),
    ("bastion", "Azure Bastion", "Networking", "Microsoft.Network", "bastionHosts", "bastions"),
    ("natgw", "NAT Gateway", "Networking", "Microsoft.Network", "natGateways", "nat"),
    ("vnetgw", "VPN / ExpressRoute gateway", "Networking", "Microsoft.Network", "virtualNetworkGateways", "virtual-network-gateways"),
    ("la", "Log Analytics", "Monitoring", "Microsoft.OperationalInsights", "workspaces", "log-analytics-workspaces"),
    ("rsv", "Recovery Services vault", "Management", "Microsoft.RecoveryServices", "vaults", "recovery-services-vaults"),
]

SOURCES = [
    {"name": "Regions, geography, coordinates, zones", "command": "az account list-locations"},
    {"name": "Service availability per region", "command": "az provider list (resourceTypes[].locations, zoneMappings)"},
    {"name": "VM SKUs, zones and subscription restrictions",
     "command": "az rest GET /subscriptions/{id}/providers/Microsoft.Compute/skus?$filter=location eq '<region>'"},
    {"name": "Functions Flex Consumption regions",
     "command": "az rest GET /subscriptions/{id}/providers/Microsoft.Web/geoRegions?sku=FlexConsumption"},
    {"name": "Azure Managed Redis SKUs with a pay-as-you-go price in the region",
     "command": "az rest GET https://prices.azure.com/api/retail/prices (Azure Managed Redis meters)"},
]

AMR_TIERS = ["Memory Optimized", "Balanced", "Compute Optimized", "Flash Optimized"]


def _size(sku):
    m = re.search(r"(\d+)", sku)
    return int(m.group(1)) if m else 0


def amr_preview(sku):
    """Preview SKUs per Microsoft Learn (Scale an Azure Managed Redis instance):
    in-memory M500/B500/X500 and higher, and Flash Optimized A2000 and A4500."""
    n = _size(sku)
    if sku[:1] in ("M", "B", "X"):
        return n >= 500
    return sku in ("A2000", "A4500")


def service_availability(providers, flex_display_names, by_display):
    """Return {service_id: {region_name: [zones]}} (a key means available)."""
    index = {}
    for p in providers or []:
        for t in p.get("types") or []:
            index[(p["ns"].lower(), (t.get("t") or "").lower())] = t
    out = {}
    for sid, _name, _cat, ns, rtype, _icon in SERVICES:
        regions = {}
        if rtype.startswith("geoRegions:"):
            for dn in flex_display_names or []:
                n = by_display.get(_norm(dn))
                if n:
                    regions[n] = []
        else:
            t = index.get((ns.lower(), rtype.lower()))
            if t:
                for loc in t.get("l") or []:
                    n = by_display.get(_norm(loc))
                    if n:
                        regions[n] = []
                for zm in t.get("z") or []:
                    n = by_display.get(_norm(zm.get("location")))
                    if n and n in regions:
                        regions[n] = sorted(zm.get("zones") or [])
        out[sid] = regions
    return out


def _norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def build_documents(regions, vm, vm_columns, services, prices, generated_at, meta):
    names = [r["name"] for r in regions]
    pos = {n: i for i, n in enumerate(names)}
    catalog = [{"id": s[0], "name": s[1], "category": s[2],
                "source": s[3] + "/" + s[4] if not s[4].startswith("geoRegions") else "Microsoft.Web/geoRegions?sku=FlexConsumption",
                "icon": s[5]} for s in SERVICES]

    region_docs, summary_regions = {}, []
    vm_index, amr_regions = {}, {}
    totals = {"vmAvailablePairs": 0}
    for r in regions:
        n = r["name"]
        rows = (vm.get(n) or {}).get("rows") or []
        stale = (vm.get(n) or {}).get("stale", False)
        avail = [x for x in rows if x[20] == "available"]
        fams = {}
        for x in avail:
            fams[x[1]] = fams.get(x[1], 0) + 1
        totals["vmAvailablePairs"] += len(avail)
        for x in rows:
            e = vm_index.get(x[0])
            if e is None:
                e = vm_index[x[0]] = {"n": x[0], "f": x[1], "c": x[3], "m": x[4], "g": x[5], "a": x[6],
                                     "ok": [], "rs": [], "zn": []}
            if x[20] == "available":
                e["ok"].append(pos[n])
                if x[18]:
                    e["zn"].append(pos[n])
            else:
                e["rs"].append(pos[n])

        amr_zones = services.get("amr", {}).get(n)
        skus = []
        for sku, info in (prices.get(n) or {}).items():
            skus.append({"sku": sku, "tier": info["tier"], "usdPerHour": info["usdPerHour"],
                         "preview": amr_preview(sku)})
        skus.sort(key=lambda s: (AMR_TIERS.index(s["tier"]) if s["tier"] in AMR_TIERS else 9, _size(s["sku"])))
        amr = {"available": amr_zones is not None, "zones": amr_zones or [], "skus": skus}
        amr_regions[n] = {"a": amr["available"], "z": amr["zones"],
                          "s": {s["sku"]: s["usdPerHour"] for s in skus}}

        svc = {}
        for sid, by_region in services.items():
            if n in by_region:
                svc[sid] = 2 if by_region[n] else 1
        svc_detail = {sid: by_region[n] for sid, by_region in services.items() if n in by_region}

        summary_regions.append(dict(r, **{
            "vm": {"available": len(avail), "restricted": len(rows) - len(avail),
                   "zonal": sum(1 for x in avail if x[18]), "families": len(fams), "stale": stale},
            "amr": {"available": amr["available"], "zonal": bool(amr["zones"]), "skus": len(skus)},
            "svc": svc,
        }))
        region_docs[n] = dict(r, **{
            "generatedAt": generated_at,
            "vm": {"columns": vm_columns, "rows": rows, "stale": stale,
                   "families": dict(sorted(fams.items(), key=lambda kv: -kv[1]))},
            "amr": amr,
            "services": svc_detail,
        })

    amr_tiers = {}
    for n, a in amr_regions.items():
        for sku in a["s"]:
            t = next((s["tier"] for s in region_docs[n]["amr"]["skus"] if s["sku"] == sku), "")
            amr_tiers.setdefault(t, set()).add(sku)
    amr_tiers = [{"tier": t, "skus": sorted(v, key=_size), "preview": [s for s in v if amr_preview(s)]}
                 for t, v in sorted(amr_tiers.items(), key=lambda kv: AMR_TIERS.index(kv[0]) if kv[0] in AMR_TIERS else 9)]

    kpis = {
        "regions": len(regions),
        "regionsWithZones": sum(1 for r in regions if r["zones"]),
        "vmSkus": sum(1 for e in vm_index.values() if e["ok"]),
        "vmAvailablePairs": totals["vmAvailablePairs"],
        "amrRegions": sum(1 for a in amr_regions.values() if a["a"]),
        "amrZonalRegions": sum(1 for a in amr_regions.values() if a["a"] and a["z"]),
        "amrPricedRegions": sum(1 for a in amr_regions.values() if a["s"]),
        "services": len(SERVICES),
    }
    meta = dict(meta)
    meta["sources"] = SOURCES
    summary = {"schema": 1, "generatedAt": generated_at, "meta": meta, "kpis": kpis,
               "services": catalog, "regions": summary_regions, "amrTiers": amr_tiers}
    vmindex = {"generatedAt": generated_at, "regions": names,
               "skus": sorted(vm_index.values(), key=lambda e: (e["f"], e["c"] or 0, e["n"]))}
    amr_doc = {"generatedAt": generated_at, "tiers": amr_tiers, "regions": amr_regions}
    return {"summary": summary, "vmindex": vmindex, "amr": amr_doc, "regions": region_docs}


def diff(previous, docs, limit=400):
    prev_idx = (previous or {}).get("vmindex")
    prev_amr = (previous or {}).get("amr")
    out = {"generatedAt": docs["summary"]["generatedAt"],
           "since": (prev_idx or {}).get("generatedAt"), "firstRun": prev_idx is None}
    new_idx = docs["vmindex"]

    def pairs(idx):
        if not idx:
            return set()
        names = idx["regions"]
        return {(e["n"], names[i]) for e in idx["skus"] for i in e["ok"]}

    if prev_idx:
        a, b = pairs(prev_idx), pairs(new_idx)
        added, removed = sorted(b - a), sorted(a - b)
        out["vm"] = {"addedCount": len(added), "removedCount": len(removed),
                     "added": [list(x) for x in added[:limit]], "removed": [list(x) for x in removed[:limit]]}
    else:
        out["vm"] = {"addedCount": 0, "removedCount": 0, "added": [], "removed": []}

    amr_changes = []
    if prev_amr:
        old, new = prev_amr.get("regions") or {}, docs["amr"]["regions"]
        for n in sorted(set(old) | set(new)):
            o, w = old.get(n) or {}, new.get(n) or {}
            if bool(o.get("a")) != bool(w.get("a")):
                amr_changes.append({"region": n, "change": "available" if w.get("a") else "removed"})
            for s in sorted(set(w.get("s") or {}) - set(o.get("s") or {})):
                amr_changes.append({"region": n, "change": "sku added", "sku": s})
            for s in sorted(set(o.get("s") or {}) - set(w.get("s") or {})):
                amr_changes.append({"region": n, "change": "sku removed", "sku": s})
    out["amr"] = amr_changes[:limit]
    return out
