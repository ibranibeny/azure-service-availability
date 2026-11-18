"""Offline tests for the collector: fake az outputs, fake Redis."""
import gzip
import json
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend", "collector"))

# --- fake redis module -------------------------------------------------------
fake_redis = types.ModuleType("redis")
DB = {}


class RedisError(Exception):
    pass


class _Pipe:
    def __init__(self, db):
        self.db, self.ops = db, []

    def set(self, k, v):
        self.ops.append(("set", k, v))

    def lpush(self, k, v):
        self.ops.append(("lpush", k, v))

    def ltrim(self, k, a, b):
        self.ops.append(("ltrim", k, a, b))

    def execute(self):
        for op in self.ops:
            if op[0] == "set":
                self.db[op[1]] = op[2]
            elif op[0] == "lpush":
                self.db.setdefault(op[1], []).insert(0, op[2])
            elif op[0] == "ltrim":
                self.db[op[1]] = self.db.get(op[1], [])[op[2]:op[3] + 1]


class Redis:
    def __init__(self, **kw):
        assert kw["ssl"] is True and kw["port"] == 10000 and kw["password"] == "redis-token"
        self.db = DB

    def get(self, k):
        return self.db.get(k)

    def pipeline(self, transaction=True):
        return _Pipe(self.db)


fake_redis.Redis = Redis
fake_redis.RedisError = RedisError
sys.modules["redis"] = fake_redis

from availability import azcli, collector  # noqa: E402

LOCS = [
    {"name": "indonesiacentral", "displayName": "Indonesia Central", "regional": "(Asia Pacific) Indonesia Central",
     "m": {"geography": "Indonesia", "geographyGroup": "Asia Pacific", "latitude": "-6.2", "longitude": "106.8",
           "physicalLocation": "Jakarta", "regionCategory": "Recommended", "pairedRegion": []},
     "zones": [{"logicalZone": "1"}, {"logicalZone": "2"}, {"logicalZone": "3"}]},
    {"name": "southeastasia", "displayName": "Southeast Asia", "regional": "(Asia Pacific) Southeast Asia",
     "m": {"geography": "Asia Pacific", "geographyGroup": "Asia Pacific", "latitude": "1.283", "longitude": "103.833",
           "physicalLocation": "Singapore", "regionCategory": "Recommended", "pairedRegion": [{"name": "eastasia"}]},
     "zones": [{"logicalZone": "1"}, {"logicalZone": "2"}, {"logicalZone": "3"}]},
]
PROVIDERS = [
    {"ns": "Microsoft.Cache", "types": [
        {"t": "redisEnterprise", "l": ["Indonesia Central", "Southeast Asia"],
         "z": [{"location": "Southeast Asia", "zones": ["2", "1", "3"]}]},
        {"t": "Redis", "l": ["Southeast Asia"], "z": None}]},
    {"ns": "Microsoft.Compute", "types": [
        {"t": "virtualMachines", "l": ["Indonesia Central", "Southeast Asia"],
         "z": [{"location": "Indonesia Central", "zones": ["1", "2", "3"]}]}]},
]


def sku(name, family, vcpu, mem, zones, restrictions=None):
    return {"n": name, "f": family, "s": name.replace("Standard_", ""), "t": "Standard", "z": zones,
            "r": restrictions or [],
            "c": [{"name": "vCPUs", "value": str(vcpu)}, {"name": "MemoryGB", "value": str(mem)},
                  {"name": "CpuArchitectureType", "value": "x64"}, {"name": "PremiumIO", "value": "True"},
                  {"name": "TrustedLaunchDisabled", "value": "False"}]}


SKUS = {
    "indonesiacentral": [sku("Standard_D2s_v5", "standardDSv5Family", 2, 8, ["1", "2", "3"]),
                         sku("Standard_E2s_v5", "standardESv5Family", 2, 16, ["1", "2", "3"],
                             [{"t": "Location", "c": "NotAvailableForSubscription", "z": None}]),
                         sku("Standard_D4s_v5", "standardDSv5Family", 4, 16, ["1", "2", "3"],
                             [{"t": "Zone", "c": "NotAvailableForSubscription", "z": ["3"]}])],
    "southeastasia": [sku("Standard_D2s_v5", "standardDSv5Family", 2, 8, ["1", "2", "3"])],
}
PRICES = {"Items": [
    {"armRegionName": "indonesiacentral", "meterName": "B0 Cache Instance", "productName": "Azure Managed Redis - Balanced", "unitPrice": 0.018},
    {"armRegionName": "indonesiacentral", "meterName": "B500 Cache Instance", "productName": "Azure Managed Redis - Balanced", "unitPrice": 11.1},
    {"armRegionName": "indonesiacentral", "meterName": "M10 Cache Instance", "productName": "Azure Managed Redis - Memory Optimized", "unitPrice": 0.24},
    {"armRegionName": "southeastasia", "meterName": "X1 Cache Instance", "productName": "Azure Managed Redis - Compute Optimized", "unitPrice": 0.16},
    {"armRegionName": "southeastasia", "meterName": "X1 Geo Replication", "productName": "Azure Managed Redis - Compute Optimized", "unitPrice": 9},
], "NextPageLink": None}

CALLS = []


def fake_run(self, *args, output="json", timeout=900, retries=1):
    CALLS.append(args)
    a = " ".join(args)
    self._record(args, 0, 0)
    if args[0] in ("login",) or a.startswith("account set"):
        return ""
    if args[0] == "version":
        return {"azure-cli": "2.93.0"}
    if a.startswith("account get-access-token"):
        return "redis-token"
    if a.startswith("account list-locations"):
        return LOCS
    if a.startswith("provider list"):
        return PROVIDERS
    if "geoRegions" in a:
        return {"value": [{"name": "Indonesia Central", "properties": {"displayName": "Indonesia Central"}}]}
    if "prices.azure.com" in a:
        return PRICES
    if "Microsoft.Compute/skus" in a:
        region = [x for x in args if x.startswith("$filter=")][0].split("'")[1]
        if region == "southeastasia" and os.environ.get("FAIL_SEA"):
            raise azcli.AzError("boom")
        return SKUS[region]
    raise AssertionError("unexpected az call: " + a)


class CollectorTest(unittest.TestCase):
    def setUp(self):
        os.environ.update({"AZURE_CLIENT_ID": "cid", "AZURE_SUBSCRIPTION_ID": "0f0f0f0f-1111-2222-3333-444444444444", "REDIS_HOST": "h",
                           "REDIS_USER_OBJECT_ID": "oid", "COLLECT_SCHEDULE": "0 0 */6 * * *"})
        azcli.AzCli.run = fake_run

    def load(self, key):
        return json.loads(gzip.decompress(DB["{asa}:v1:" + key]))

    def test_full_run(self):
        DB.clear()
        os.environ.pop("FAIL_SEA", None)
        stats = collector.run(trigger="test")
        self.assertEqual(stats["regions"], 2)
        s = self.load("summary")
        self.assertEqual(s["kpis"]["regions"], 2)
        self.assertEqual(s["kpis"]["amrRegions"], 2)
        self.assertEqual(s["kpis"]["amrZonalRegions"], 1)
        idc = [r for r in s["regions"] if r["name"] == "indonesiacentral"][0]
        self.assertEqual(idc["vm"], {"available": 2, "restricted": 1, "zonal": 2, "families": 1, "stale": False})
        self.assertEqual(idc["svc"]["funcflex"], 1)
        self.assertEqual(idc["svc"]["vm"], 2)
        self.assertNotIn("redis", idc["svc"])
        rd = self.load("region:indonesiacentral")
        cols = rd["vm"]["columns"]
        d4 = [r for r in rd["vm"]["rows"] if r[0] == "Standard_D4s_v5"][0]
        self.assertEqual(d4[cols.index("zones")], ["1", "2"])
        self.assertEqual(d4[cols.index("zonesRestricted")], ["3"])
        e2 = [r for r in rd["vm"]["rows"] if r[0] == "Standard_E2s_v5"][0]
        self.assertEqual(e2[cols.index("status")], "restricted")
        self.assertEqual([x["sku"] for x in rd["amr"]["skus"]], ["M10", "B0", "B500"])
        self.assertTrue([x for x in rd["amr"]["skus"] if x["sku"] == "B500"][0]["preview"])
        idx = self.load("vmindex")
        d2 = [e for e in idx["skus"] if e["n"] == "Standard_D2s_v5"][0]
        self.assertEqual(sorted(idx["regions"][i] for i in d2["ok"]), ["indonesiacentral", "southeastasia"])
        amr = self.load("amr")
        self.assertEqual(amr["regions"]["southeastasia"]["s"], {"X1": 0.16})
        ch = self.load("changes")
        self.assertTrue(ch["firstRun"])
        runs = DB["{asa}:v1:runs"]
        self.assertEqual(json.loads(runs[0])["ok"], True)
        # second run with a failing region keeps the previous rows and reports the change set
        os.environ["FAIL_SEA"] = "1"
        SKUS["indonesiacentral"].append(sku("Standard_D8s_v5", "standardDSv5Family", 8, 32, []))
        collector.run(trigger="test")
        s2 = self.load("summary")
        sea = [r for r in s2["regions"] if r["name"] == "southeastasia"][0]
        self.assertTrue(sea["vm"]["stale"])
        self.assertEqual(sea["vm"]["available"], 1)
        ch2 = self.load("changes")
        self.assertEqual(ch2["vm"]["added"], [["Standard_D8s_v5", "indonesiacentral"]])
        self.assertEqual(len(s2["meta"]["errors"]), 1)
        self.assertNotIn("0f0f0f0f-1111", json.dumps(s2))  # subscription id never published


if __name__ == "__main__":
    unittest.main()
