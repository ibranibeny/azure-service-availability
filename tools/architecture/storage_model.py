"""Why the Function apps need a storage account: what the Functions host keeps there and how it gets in.
Mirrors infra/main.bicep (storage account, private endpoints, roles) and what Microsoft Learn documents."""

W, H = 1320, 732
VB_TOP = -16                      # room above y=0 for the operator → management plane line
KEY = "storage"

L = "https://learn.microsoft.com/en-us/azure/"
REPO = "https://github.com/ibranibeny/azure-service-availability/blob/main/"
SRC = {
    "STORAGE": ("Storage considerations for Azure Functions", L + "azure-functions/storage-considerations"),
    "APP_SETTINGS": ("App settings reference for Azure Functions", L + "azure-functions/functions-app-settings"),
    "TIMER": ("Timer trigger for Azure Functions", L + "azure-functions/functions-bindings-timer"),
    "FLEX_HOWTO": ("Create and manage function apps in the Flex Consumption plan", L + "azure-functions/flex-consumption-how-to"),
    "FLEX_PLAN": ("Azure Functions Flex Consumption plan hosting", L + "azure-functions/flex-consumption-plan"),
    "NET": ("How to use a secured storage account with Azure Functions", L + "azure-functions/configure-networking-how-to"),
    "CONN": ("Configure connections to remote services in Azure Functions", L + "azure-functions/manage-connections"),
    "IAC": ("Automate resource deployment for your function app", L + "azure-functions/functions-infrastructure-as-code"),
    "RUN": ("Manually run a non HTTP-triggered function", L + "azure-functions/functions-manually-run-non-http"),
    "INSPECT": ("This repo: scripts/inspect-storage.sh", REPO + "scripts/inspect-storage.sh"),
}

ZONES = [
    dict(id="ops", kind="ops", box=(16, 24, 256, 120), title="Operator"),
    dict(id="entra", kind="identity", box=(296, 24, 600, 120), title="Microsoft Entra ID · contoso.day tenant", icon="tenant-properties"),
    dict(id="mgmt", kind="web", box=(920, 24, 384, 120), title="Azure management plane"),
    dict(id="rg", kind="azure", box=(296, 164, 1008, 552), title="rg-azure-service-availability · Indonesia Central",
         kicker="Azure subscription › resource group", icon="resource-groups", tx=780),
    dict(id="vnet", kind="vnet", box=(312, 308, 560, 266), title="vnet-asa-cangze · 10.62.0.0/24", icon="virtual-networks", tx=436),
    dict(id="snetf", kind="subnet", box=(326, 340, 532, 84), title="snet-functions · 10.62.0.0/26", icon="subnet", tx=436),
    dict(id="snetp", kind="subnet", box=(326, 436, 532, 124), title="snet-private-endpoints · 10.62.0.64/27", icon="subnet", tx=436),
    dict(id="st", kind="store", box=(896, 212, 392, 488), title="stasacangzeawpizgg", kicker="Storage account · StorageV2 · Standard_LRS",
         icon="storage-accounts", lock=True),
    dict(id="blob", kind="svc", box=(912, 262, 360, 244), title="Blob service · containers", icon="storage-container"),
    dict(id="table", kind="svc", box=(912, 516, 360, 76), title="Table service", icon="storage-table"),
    dict(id="queue", kind="svc", box=(912, 602, 360, 76), title="Queue service", icon="storage-queue"),
]

NODES = {
    "shell": dict(box=(32, 54, 224), icon="azure-cloud-shell", title="Azure Cloud Shell", mono="bibrani@contoso.day", sub="deploy.sh · run-collector.sh"),
    "entra": dict(box=(312, 54, 568), icon="tenant-properties", title="Microsoft Entra ID",
                  sub2="tokens for Azure Storage (https://storage.azure.com)", sub="issued to the apps' user-assigned managed identities"),
    "arm": dict(box=(936, 54, 352), icon="azure-a", title="Azure Resource Manager", mono="management.azure.com", sub="Bicep · keys list · inspect-storage.sh"),
    "api": dict(box=(312, 220, 224), icon="function-apps", title="Function app", mono="func-asa-api-cangze", sub="identity id-asa-api", pill="API"),
    "collector": dict(box=(552, 220, 236), icon="function-apps", title="Function app", mono="func-asa-collector-cangze", sub="identity id-asa-collector",
                      pill="COLLECTOR", timer="0 0 */6 * * *  UTC"),
    "portA": dict(box=(347, 372, 150, 40), icon="subnet", title="VNet integration", kind="port"),
    "portC": dict(box=(625, 372, 150, 40), icon="subnet", title="VNet integration", kind="port"),
    "pe": dict(box=(380, 458, 336), icon="private-endpoints", title="Private endpoints", sub2="blob · queue · table", sub="one NIC each in snet-private-endpoints"),
    "dns": dict(box=(312, 612, 220), icon="dns-zones", title="Private DNS zones", mono="privatelink.*", sub="blob · queue · table zones"),
    "pkgC": dict(box=(928, 294, 328, 44), kind="row", icon="blob-block", title="app-package-collector", sub="collector package · 52 MB, Azure CLI inside"),
    "pkgA": dict(box=(928, 346, 328, 44), kind="row", icon="blob-block", title="app-package-api", sub="API package · 7 MB"),
    "hosts": dict(box=(928, 398, 328, 44), kind="row", plain=True, icon="blob-block", title="Functions host state", sub="timer lock · schedule status (use_monitor)"),
    "secrets": dict(box=(928, 450, 328, 44), kind="row", plain=True, icon="blob-block", title="Function keys", sub="master, host and function keys (default store)"),
    "diag": dict(box=(928, 544, 328, 40), kind="row", plain=True, icon="storage-table", title="Diagnostic events", sub="written by the Functions host when it hits problems"),
    "noq": dict(box=(928, 630, 328, 40), kind="row", plain=True, icon="storage-queue", title="Not used by these two apps", sub="blob or queue triggers and Durable would use it"),
}

SEGS = {
    "sh_arm": dict(pts=[(180, 54), (180, 6), (1112, 6), (1112, 54)], cat="ops", ends=("shell", "arm"),
                   label=("az functionapp keys list · inspect-storage.sh", 646, 0, "middle")),
    "sh_api": dict(pts=[(256, 104), (284, 104), (284, 256), (312, 256)], cat="ops", ends=("shell", "api"),
                   label=("zip deploy", 290, 158, "start")),
    "sh_col": dict(pts=[(256, 104), (284, 104), (284, 194), (760, 194), (760, 220)], cat="ops", ends=("shell", "collector"), hops=[422, 720]),
    "api_entra": dict(pts=[(422, 220), (422, 126)], cat="identity", ends=("api", "entra"), label=("token", 430, 180, "start")),
    "col_entra": dict(pts=[(720, 220), (720, 126)], cat="identity", ends=("collector", "entra"), label=("token", 728, 160, "start")),
    "api_port": dict(pts=[(422, 292), (422, 372)], cat="private", ends=("api", "portA")),
    "col_port": dict(pts=[(700, 292), (700, 372)], cat="private", ends=("collector", "portC")),
    "portA_pe": dict(pts=[(422, 412), (422, 458)], cat="private", ends=("portA", "pe")),
    "portC_pe": dict(pts=[(700, 412), (700, 458)], cat="private", ends=("portC", "pe")),
    "pe_pkgC": dict(pts=[(716, 472), (884, 472), (884, 316), (928, 316)], cat="private", ends=("pe", "pkgC")),
    "pe_pkgA": dict(pts=[(716, 472), (884, 472), (884, 368), (928, 368)], cat="private", ends=("pe", "pkgA")),
    "pe_hosts": dict(pts=[(716, 472), (884, 472), (884, 420), (928, 420)], cat="private", ends=("pe", "hosts")),
    "pe_secrets": dict(pts=[(716, 472), (928, 472)], cat="private", ends=("pe", "secrets"), label=("blob", 760, 466, "middle")),
    "pe_diag": dict(pts=[(716, 498), (878, 498), (878, 564), (928, 564)], cat="private", ends=("pe", "diag"), label=("table", 800, 492, "middle")),
    "pe_queue": dict(pts=[(716, 522), (866, 522), (866, 650), (928, 650)], cat="private", ends=("pe", "noq"), label=("queue", 840, 516, "middle")),
    "dns": dict(pts=[(422, 612), (422, 574)], cat="link", ends=("dns", "vnet"), label=("linked to the VNet", 430, 596, "start"), arrow=False),
    "arm_st": dict(pts=[(1180, 126), (1180, 212)], cat="ops", ends=("arm", "st"), label=("management plane", 1188, 190, "start")),
}

FLOW_ORDER = ["pkg", "timer", "keys", "mgmt"]

FLOWS = [
    dict(id="pkg", name="Deploy and start", short="Deploy", tagline="where the code lives on Flex Consumption", steps=[
        dict(title="Upload the packages", src="FLEX_HOWTO",
             hops=[("sh_col", 1, "collector.zip · 52 MB"), ("sh_api", 1, "api.zip · 7 MB")],
             text="deploy.sh runs az functionapp deployment source config-zip for each app. The upload goes to the app's deployment endpoint, which stores it in the app's deployment container."),
        dict(title="Kept in a blob container", focus=["pkgC", "pkgA"], hops=[], src="FLEX_HOWTO",
             text="Each app's package is stored in its own deployment container (functionAppConfig.deployment.storage), here app-package-collector and app-package-api, accessed with the app's user-assigned identity."),
        dict(title="Token for Azure Storage", src="FLEX_HOWTO",
             hops=[("col_entra", 1, "token request"), ("col_entra", -1, "Entra token")],
             text="The package is read with the identity set in functionAppConfig.deployment.storage (UserAssignedIdentity, each app's own identity), which gets a Microsoft Entra token. Shared key access is disabled on this account."),
        dict(title="Fetch the package privately", src="FLEX_PLAN",
             hops=[("col_port", 1, "GET package"), ("portC_pe", 1, ""), ("pe_pkgC", 1, ""), ("pe_pkgC", -1, "52 MB"), ("portC_pe", -1, ""), ("col_port", -1, "")],
             text="At startup the app fetches its package and runs from it; Flex Consumption has no Azure Files content share. With public access off this worked over the VNet path in the reference run (tested, not spelled out on Learn)."),
    ]),
    dict(id="timer", name="Timer: once, on time", short="Timer", tagline="what the timer trigger keeps in blob storage", steps=[
        dict(title="Timer due", focus=["collector"], hops=[], src="TIMER",
             text="At 00:00, 06:00, 12:00 and 18:00 UTC the collection is due. Timer triggers depend on blob storage, reached through the host storage connection (AzureWebJobsStorage)."),
        dict(title="Token for Azure Storage", src="CONN",
             hops=[("col_entra", 1, "token request"), ("col_entra", -1, "Entra token")],
             text="Host storage uses an identity-based connection (AzureWebJobsStorage__credential = managedidentity, __clientId). Storage Blob Data Owner is the minimum role for it."),
        dict(title="Take the lock", src="TIMER",
             hops=[("col_port", 1, "acquire lock"), ("portC_pe", 1, ""), ("pe_hosts", 1, ""), ("pe_hosts", -1, "lock held"), ("portC_pe", -1, ""), ("col_port", -1, "")],
             text="The host takes a storage lock so only one instance runs the timer, even after the app scales out, and it doesn't fire again while a run is still going."),
        dict(title="Collect", focus=["collector"], hops=[], src="TIMER",
             text="The collection runs, about 90 seconds. Its results go to Azure Managed Redis, not to this storage account. A failed run isn't retried; the next one is at the next schedule."),
        dict(title="Record the schedule", src="TIMER",
             hops=[("col_port", 1, "schedule status"), ("portC_pe", 1, ""), ("pe_hosts", 1, "")],
             text="Schedule monitoring (use_monitor=True in function_app.py) saves the schedule's occurrences so it survives restarts. A late run gets past_due and logs 'Schedule is past due'."),
    ]),
    dict(id="keys", name="Keys and a manual run", short="Keys", tagline="the master key that run-collector.sh uses", steps=[
        dict(title="Ask for the master key", src="RUN",
             hops=[("sh_arm", 1, "az functionapp keys list"), ("sh_arm", -1, "master key")],
             text="run-collector.sh asks Azure Resource Manager for the collector's master key. Treat it as a secret: it can call every admin endpoint of the app."),
        dict(title="Where the key comes from", src="APP_SETTINGS",
             hops=[("col_port", 1, "read keys"), ("portC_pe", 1, ""), ("pe_secrets", 1, ""), ("pe_secrets", -1, "keys"), ("portC_pe", -1, ""), ("col_port", -1, "")],
             text="The keys come from the app, and the Functions host keeps them in blob storage by default (AzureWebJobsSecretStorageType = blob) in the host storage account."),
        dict(title="Run the timer function now", src="RUN",
             hops=[("sh_col", 1, "POST /admin/functions/collect")],
             text="POST /admin/functions/collect with the master key in x-functions-key returns 202 Accepted and runs the function once, useful to fill the cache right after a deployment."),
    ]),
    dict(id="mgmt", name="What you can see from outside", short="Inspect", tagline="management plane yes, data plane no", steps=[
        dict(title="List settings and containers", src="INSPECT",
             hops=[("sh_arm", 1, "inspect-storage.sh"), ("arm_st", 1, "list (no data)"), ("arm_st", -1, "names, settings"), ("sh_arm", -1, "")],
             text="inspect-storage.sh lists settings, private endpoints, containers, queues, tables and role assignments through Azure Resource Manager, so it works even though public access is off."),
        dict(title="Contents stay private", focus=["pkgC", "pkgA", "hosts", "secrets", "diag", "pe"], hops=[], src="NET",
             text="Blob, queue and table contents are reachable only from inside the VNet through the private endpoints. The portal's storage browser and Cloud Shell can't open them, which is the point."),
    ]),
]

TITLE = "Why the Function apps need a storage account"
DESC = ("The two Flex Consumption Function apps use one storage account, reached only through private endpoints with "
        "managed-identity tokens: deployment packages, the timer lock and schedule status, function keys and host diagnostics. "
        "The dashboard data itself lives in Azure Managed Redis.")
FLOWCOL = {"pkg": "f-deploy", "timer": "f-collect", "keys": "f-signedin", "mgmt": "f-guest"}
BADGE_MANUAL = {("pkg", 1): (1256, 277), ("timer", 0): (552, 222), ("timer", 3): (552, 292), ("mgmt", 1): (1236, 232)}
STATIC_FLOWS = ()
RING = ("timer", 0, "collector")
TAG_LEFT_X = 1150
CAP_WIDTH = 950
NOTES = []
LEGEND = dict(box=(16, 164, 256, 236),
              cats=[("public", "HTTPS to a public endpoint"), ("private", "private: VNet → private endpoint"),
                    ("identity", "identity: Entra tokens"), ("ops", "deployment and operations"), ("link", "private DNS zone link")],
              lock="public network access disabled")
BULLETS = [
    dict(box=(16, 416, 256, 124), title="Account settings (Bicep)",
         items=["Public network access: Disabled", "Shared key access: Disabled", "Entra ID (OAuth) by default · TLS 1.2",
                "No anonymous blob access", "Same region as the apps"]),
    dict(box=(16, 556, 256, 100), title="Storage roles per app identity",
         items=["Blob Data Owner: host storage", "Table Data Contributor: diagnostics", "Queue Data Contributor: not needed today"]),
    dict(box=(548, 600, 324, 92), title="Not in this storage account",
         items=["The dashboard data: that's in Azure Managed Redis", "An Azure Files content share: Flex has none",
                "Keys or connection strings in app settings"]),
]
WIDGET = dict(
    title="Why a storage account? Watch what goes in and out",
    intro="Pick a flow and press play. Each step names the setting behind it and links to its Microsoft Learn source.",
    fine='Static image: <a href="assets/img/storage-account.svg" target="_blank" rel="noopener">storage-account.svg</a> · full solution: <a href="./#architecture">Architecture tab</a>.',
    idle_name="Four flows", idle_tag="deploy and start · timer · keys · what you can see from outside",
    aria="Storage account diagram. Space plays or pauses the animation, the arrow keys step through it, F opens full screen.",
    storage_key="asa.storagePlay", h="h3")
