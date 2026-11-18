"""Architecture model: zones, nodes, connectors and the four traffic flows.
Everything here mirrors what infra/main.bicep and the Function apps actually deploy and do."""

W, H = 1520, 816

LEARN = {
    "NET": "https://learn.microsoft.com/en-us/azure/azure-functions/functions-networking-options",
    "TIMER": "https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-timer",
    "CLI_MI": "https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-managed-identity",
    "SKUS": "https://learn.microsoft.com/en-us/rest/api/compute/resource-skus/list",
    "PRICES": "https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices",
    "REDIS_ENTRA": "https://learn.microsoft.com/en-us/azure/redis/entra-for-authentication",
    "REDIS_PL": "https://learn.microsoft.com/en-us/azure/redis/private-link",
    "PE_DNS": "https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns",
    "APP_SETTINGS": "https://learn.microsoft.com/en-us/azure/azure-functions/functions-app-settings",
    "FLEX_HOWTO": "https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-how-to",
    "AUTHCODE": "https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow",
    "ACCESS_TOKENS": "https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens",
    "CLAIMS": "https://learn.microsoft.com/en-us/entra/identity-platform/claims-validation",
    "APPI": "https://learn.microsoft.com/en-us/azure/azure-monitor/app/azure-ad-authentication",
    "CORS": "https://learn.microsoft.com/en-us/azure/azure-functions/functions-how-to-use-azure-function-app-settings",
    "OUTBOUND": "https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/default-outbound-access",
    "DEPLOY": "https://learn.microsoft.com/en-us/azure/azure-functions/functions-deployment-technologies",
    "PAGES": "https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site",
    "WAF": "https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azure-functions",
}
REPO = "https://github.com/ibranibeny/azure-service-availability/blob/main/"
SRC = {
    "NET": ("Azure Functions networking options", LEARN["NET"]),
    "TIMER": ("Timer trigger for Azure Functions", LEARN["TIMER"]),
    "CLI_MI": ("Sign in to Azure CLI with a managed identity", LEARN["CLI_MI"]),
    "SKUS": ("Resource Skus - List (REST)", LEARN["SKUS"]),
    "PRICES": ("Azure Retail Prices REST API", LEARN["PRICES"]),
    "REDIS_ENTRA": ("Microsoft Entra ID for Azure Managed Redis authentication", LEARN["REDIS_ENTRA"]),
    "REDIS_PL": ("Azure Managed Redis with Azure Private Link", LEARN["REDIS_PL"]),
    "PE_DNS": ("Azure private endpoint DNS zone values", LEARN["PE_DNS"]),
    "APP_SETTINGS": ("App settings reference for Azure Functions", LEARN["APP_SETTINGS"]),
    "FLEX_HOWTO": ("Create and manage function apps in the Flex Consumption plan", LEARN["FLEX_HOWTO"]),
    "AUTHCODE": ("Microsoft identity platform and OAuth 2.0 authorization code flow", LEARN["AUTHCODE"]),
    "ACCESS_TOKENS": ("Access tokens in the Microsoft identity platform", LEARN["ACCESS_TOKENS"]),
    "APPI": ("Microsoft Entra authentication for Application Insights", LEARN["APPI"]),
    "CORS": ("Manage your function app: CORS", LEARN["CORS"]),
    "DEPLOY": ("Deployment technologies in Azure Functions", LEARN["DEPLOY"]),
    "PAGES": ("GitHub Docs: configuring a publishing source for GitHub Pages", LEARN["PAGES"]),
    "GUEST": ("This repo: backend/api/availability_api/guest.py", REPO + "backend/api/availability_api/guest.py"),
    "API": ("This repo: backend/api/function_app.py", REPO + "backend/api/function_app.py"),
    "RUN": ("This repo: scripts/run-collector.sh", REPO + "scripts/run-collector.sh"),
}

# kind -> styling class.  (x, y, w, h)
ZONES = [
    dict(id="entra", kind="identity", box=(288, 16, 920, 112), title="Microsoft Entra ID · contoso.day tenant", icon="tenant-properties"),
    dict(id="ops", kind="ops", box=(1236, 16, 268, 112), title="Operator"),
    dict(id="web", kind="web", box=(16, 150, 248, 530), title="Public internet"),
    dict(id="rg", kind="azure", box=(288, 150, 920, 650), title="rg-azure-service-availability · Indonesia Central",
         kicker="Azure subscription › resource group", icon="resource-groups", tx=340),
    dict(id="vnet", kind="vnet", box=(304, 344, 888, 306), title="vnet-asa-cangze · 10.62.0.0/24", icon="virtual-networks", tx=432),
    dict(id="snetf", kind="subnet", box=(318, 376, 860, 96), title="snet-functions · 10.62.0.0/26 · delegated to Microsoft.App/environments", icon="subnet", tx=432),
    dict(id="snetp", kind="subnet", box=(318, 486, 860, 154), title="snet-private-endpoints · 10.62.0.64/27", icon="subnet", tx=432),
    dict(id="ext", kind="web", box=(1236, 150, 268, 380), title="Microsoft public endpoints"),
]

# card: (x, y, w[, h]) title, mono (resource / host), sub (facts)
NODES = {
    "browser": dict(box=(24, 252, 232), icon="browser", title="Browser", sub2="dashboard app (SPA)", sub="guest or contoso.day user"),
    "pages": dict(box=(24, 418, 232), icon="folder-website", title="GitHub Pages", mono="ibranibeny.github.io", sub="static site from /docs"),
    "repo": dict(box=(24, 584, 232), icon="code", title="GitHub repository", mono="azure-service-availability", sub="docs · backend · infra"),
    "shell": dict(box=(1260, 46, 220), icon="azure-cloud-shell", title="Azure Cloud Shell", mono="bibrani@contoso.day", sub="bash scripts/deploy.sh"),
    "entra": dict(box=(316, 46, 704), icon="tenant-properties", title="Microsoft Entra ID",
                  sub2="sign-in (OAuth 2.0 + PKCE) · access tokens · signing keys (JWKS)",
                  sub="issues tokens to the two managed identities",
                  chips=[("app-registrations", "Dashboard app · SPA, PKCE"), ("app-registrations", "API app · Availability.Read")]),
    "api": dict(box=(304, 252, 224), icon="function-apps", title="Function app", mono="func-asa-api-cangze", sub="Flex Consumption · HTTP", pill="API"),
    "mi": dict(box=(632, 252, 224), icon="managed-identities", title="Managed identities", mono="id-asa-api, -collector", sub="user-assigned · no secrets"),
    "collector": dict(box=(960, 252, 224), icon="function-apps", title="Function app", mono="func-asa-collector-cangze", sub="Flex Consumption · timer", pill="COLLECTOR",
                      timer="0 0 */6 * * *  UTC"),
    "portA": dict(box=(341, 416, 150, 40), icon="subnet", title="VNet integration", kind="port"),
    "portC": dict(box=(997, 416, 150, 40), icon="subnet", title="VNet integration", kind="port"),
    "pe": dict(box=(610, 532, 276), icon="private-endpoints", title="Private endpoints", sub2="redis · blob · queue · table", sub="NICs in snet-private-endpoints"),
    "dns": dict(box=(304, 700, 200), icon="dns-zones", title="Private DNS zones", mono="privatelink.*", sub="redis · blob · queue · table"),
    "redis": dict(box=(520, 700, 220), icon="azure-managed-redis", title="Azure Managed Redis", mono="redis-asa-cangze", sub="Balanced B0 · TLS 10000", lock=True),
    "storage": dict(box=(756, 700, 212), icon="storage-accounts", title="Storage account", mono="stasacangzeawpizgg", sub="packages + host storage", lock=True),
    "appi": dict(box=(984, 700, 200), icon="application-insights", title="Application Insights", mono="appi-asa-cangze", sub="+ Log Analytics"),
    "arm": dict(box=(1260, 252, 220), icon="azure-a", title="Azure Resource Manager", mono="management.azure.com", sub="SKUs · providers · regions"),
    "prices": dict(box=(1260, 432, 220), icon="cost-management", title="Azure Retail Prices API", mono="prices.azure.com", sub="Managed Redis list prices"),
}

# connectors: points (orthogonal), category, from, to, label (text, x, y, anchor[, rotate]), hops (x on horizontal runs)
SEGS = {
    "br_pages": dict(pts=[(140, 324), (140, 418)], cat="public", ends=("browser", "pages"), label=("HTTPS", 148, 375, "start")),
    "repo_pages": dict(pts=[(140, 584), (140, 490)], cat="ops", ends=("repo", "pages"), label=("publish /docs", 148, 541, "start")),
    "br_entra": dict(pts=[(140, 252), (140, 82), (316, 82)], cat="identity", ends=("browser", "entra"), label=("sign-in · PKCE", 148, 222, "start")),
    "br_api": dict(pts=[(256, 288), (304, 288)], cat="public", ends=("browser", "api"), label=("HTTPS", 280, 279, "middle")),
    "api_entra": dict(pts=[(330, 252), (330, 118)], cat="identity", ends=("api", "entra"), label=("JWKS", 338, 238, "start")),
    "api_mi": dict(pts=[(528, 288), (632, 288)], cat="identity", ends=("api", "mi"), label=("token", 580, 279, "middle")),
    "col_mi": dict(pts=[(960, 288), (856, 288)], cat="identity", ends=("collector", "mi"), label=("token", 908, 279, "middle")),
    "mi_entra": dict(pts=[(744, 252), (744, 118)], cat="identity", ends=("mi", "entra"), label=("managed-identity tokens", 752, 238, "start")),
    "api_port": dict(pts=[(416, 324), (416, 416)], cat="private", ends=("api", "portA")),
    "portA_pe": dict(pts=[(416, 456), (416, 568), (610, 568)], cat="private", ends=("portA", "pe"), label=("private endpoint", 510, 559, "middle")),
    "col_port": dict(pts=[(1072, 324), (1072, 416)], cat="private", ends=("collector", "portC")),
    "portC_pe": dict(pts=[(1072, 456), (1072, 568), (886, 568)], cat="private", ends=("portC", "pe"), label=("private endpoint", 980, 559, "middle")),
    "pe_redis": dict(pts=[(630, 604), (630, 700)], cat="private", ends=("pe", "redis"), label=("TLS 10000", 638, 680, "start")),
    "pe_sto": dict(pts=[(862, 604), (862, 700)], cat="private", ends=("pe", "storage"), label=("blob · queue · table", 870, 680, "start")),
    "dns": dict(pts=[(404, 700), (404, 650)], cat="link", ends=("dns", "vnet"), label=("linked to the VNet", 412, 680, "start"), arrow=False),
    "col_arm": dict(pts=[(1184, 276), (1260, 276)], cat="public", ends=("collector", "arm")),
    "col_prices": dict(pts=[(1184, 300), (1222, 300), (1222, 468), (1260, 468)], cat="public", ends=("collector", "prices")),
    "col_appi": dict(pts=[(1184, 312), (1200, 312), (1200, 736), (1184, 736)], cat="telemetry", ends=("collector", "appi"),
                     label=("telemetry", 1200, 560, "middle", -90)),
    "sh_arm": dict(pts=[(1460, 118), (1460, 252)], cat="ops", ends=("shell", "arm"), label=("Bicep", 1452, 200, "end")),
    "sh_entra": dict(pts=[(1260, 82), (1020, 82)], cat="ops", ends=("shell", "entra"), label=("app registrations", 1140, 73, "middle")),
    "sh_col": dict(pts=[(1260, 104), (1228, 104), (1228, 216), (1140, 216), (1140, 252)], cat="ops", ends=("shell", "collector"),
                   label=("package deploy", 1000, 207, "middle")),
    "sh_api": dict(pts=[(1260, 104), (1228, 104), (1228, 216), (470, 216), (470, 252)], cat="ops", ends=("shell", "api"), hops=[744]),
}

FLOW_ORDER = ["collect", "guest", "signedin", "deploy"]

# ---- presentation settings used by build.py ----
KEY = "arch"                                   # output names: docs/assets/img/architecture*.svg, arch-flows.js
TITLE = "Azure Service Availability architecture"
DESC = ("GitHub Pages dashboard in the browser; optional Microsoft Entra ID sign-in; API and collector Function apps "
        "(Flex Consumption, Indonesia Central) with user-assigned managed identities; VNet integration and private endpoints "
        "to Azure Managed Redis and Storage; the collector calls Azure Resource Manager and the Azure Retail Prices API every 6 hours.")
FLOWCOL = {"collect": "f-collect", "guest": "f-guest", "signedin": "f-signedin", "deploy": "f-deploy"}
BADGE_MANUAL = {("collect", 0): (950, 247), ("guest", 2): (296, 246)}
STATIC_FLOWS = ("collect", "signedin")           # numbered badges drawn on the static image
RING = ("collect", 0, "collector")               # pulse the timer pill on this step
TAG_LEFT_X = 1300                               # packet tags flip left beyond this x
CAP_WIDTH = 1150                                # caption wrap width in the self-running SVG
NOTES = [("All outbound traffic from both apps leaves through this subnet", 744, 434, "middle", 500),
         ("internet egress is platform-managed here · a NAT gateway gives a fixed IP", 744, 450, "middle", 500)]
LEGEND = dict(box=(1236, 548, 268, 252),
              cats=[("public", "HTTPS to a public endpoint"), ("private", "private: VNet → private endpoint"),
                    ("identity", "identity: tokens, signing keys"), ("telemetry", "telemetry"),
                    ("ops", "deployment and operations"), ("link", "private DNS zone link")],
              lock="public network access disabled")
BULLETS = [dict(box=(16, 696, 248, 104), title="Security by design",
                items=["No secrets in the page or the repo", "Managed identities for ARM, Redis, storage",
                       "Redis and storage: no public access, no keys", "API CORS: ibranibeny.github.io only"])]
WIDGET = dict(
    title="Architecture",
    intro="What runs where and how the traffic flows. Pick a flow and press play: packets travel hop by hop, and each step names the setting behind it with its Microsoft Learn source.",
    fine='Also as images: <a href="assets/img/architecture.svg" target="_blank" rel="noopener">static diagram</a> · <a href="assets/img/architecture-animated.svg" target="_blank" rel="noopener">self-running animation</a> (the one in the README).',
    idle_name="Four flows", idle_tag="scheduled collection · guest read · signed-in read · deploy & publish",
    aria="Architecture diagram. Space plays or pauses the traffic animation, the arrow keys step through it, F opens full screen.",
    storage_key="asa.archPlay")

# hop: (segment, direction 1 = along the arrow / -1 = back, packet tag, burst)
FLOWS = [
    dict(id="collect", name="Scheduled collection", short="Collect", tagline="every 6 hours, Azure CLI in Azure Functions", steps=[
        dict(title="Timer fires", focus=["collector"], hops=[], src="TIMER",
             text="The timer trigger 0 0 */6 * * * runs at 00:00, 06:00, 12:00 and 18:00 UTC (07, 13, 19 and 01 WIB). Flex Consumption on Linux always uses UTC for schedules."),
        dict(title="Sign in as the managed identity", src="CLI_MI",
             hops=[("col_mi", 1, "az login --identity"), ("mi_entra", 1, ""), ("mi_entra", -1, "ARM token"), ("col_mi", -1, "")],
             text="az login --identity --client-id gets an Azure Resource Manager token for id-asa-collector, which has Reader on the subscription and nothing else."),
        dict(title="Regions, providers, Flex regions", src="NET",
             hops=[("col_arm", 1, "list-locations · providers"), ("col_arm", -1, "JSON")],
             text="az account list-locations, az provider list and az rest on Microsoft.Web/geoRegions. Like every outbound call from a Flex Consumption app, it leaves through snet-functions."),
        dict(title="VM sizes for every region", src="SKUS",
             hops=[("col_arm", 1, "Compute/skus × 65", 8), ("col_arm", -1, "SKUs", 8)],
             text="az rest GET Microsoft.Compute/skus?$filter=location eq '<region>' for 65 regions, 8 at a time: about 5 s per region instead of about 2 min with az vm list-skus. Restrictions flag sizes that are NotAvailableForSubscription."),
        dict(title="Managed Redis list prices", src="PRICES",
             hops=[("col_prices", 1, "$filter"), ("col_prices", -1, "prices")],
             text="The Azure Retail Prices API, filtered to Azure Managed Redis, needs no sign-in and returns up to 1,000 items per page; the collector follows NextPageLink."),
        dict(title="Token for Redis", src="REDIS_ENTRA",
             hops=[("col_mi", 1, "token for redis.azure.com"), ("mi_entra", 1, ""), ("mi_entra", -1, "Entra token"), ("col_mi", -1, "")],
             text="az account get-access-token --resource https://redis.azure.com. The cache accepts Microsoft Entra tokens only (access keys are disabled); the username is the identity's object ID."),
        dict(title="Write the snapshot privately", src="REDIS_PL",
             hops=[("col_port", 1, "MULTI/EXEC"), ("portC_pe", 1, ""), ("pe_redis", 1, ""), ("pe_redis", -1, "OK"), ("portC_pe", -1, ""), ("col_port", -1, "")],
             text="Through VNet integration to the Redis private endpoint (privatelink.redis.azure.net, TLS port 10000). One MULTI/EXEC transaction writes the gzip JSON documents, the change log and the run record."),
        dict(title="Telemetry", src="APPI",
             hops=[("col_appi", 1, "trace")],
             text="'Collection finished' (65 regions, 67,469 VM rows, 0 errors on 18 Nov 2026) goes to Application Insights with Microsoft Entra authentication; local authentication is disabled."),
    ]),
    dict(id="guest", name="Guest read", short="Guest", tagline="anyone with the link, read-only, no sign-in", steps=[
        dict(title="Open the dashboard", src="PAGES",
             hops=[("br_pages", 1, "GET /"), ("br_pages", -1, "HTML · JS")],
             text="The browser loads the static site from GitHub Pages: HTML, JavaScript and config.js, which holds public IDs only. There are no secrets in the page or the repo."),
        dict(title="Call the API without a token", src="CORS",
             hops=[("br_api", 1, "GET /api/summary")],
             text="GET /api/summary on func-asa-api-cangze with no Authorization header. CORS on the Function app allows https://ibranibeny.github.io only."),
        dict(title="Guest mode", focus=["api"], hops=[], src="GUEST",
             text="No token means a read-only guest: 120 requests a minute per address and no collector error details. A request with a bad token is refused, never treated as a guest."),
        dict(title="Token for Redis", src="REDIS_ENTRA",
             hops=[("api_mi", 1, "token for redis.azure.com"), ("mi_entra", 1, ""), ("mi_entra", -1, "Entra token"), ("api_mi", -1, "")],
             text="The API's own managed identity (id-asa-api) gets a Microsoft Entra token for https://redis.azure.com and reuses it until shortly before it expires."),
        dict(title="Read the snapshot privately", src="REDIS_PL",
             hops=[("api_port", 1, "GET summary"), ("portA_pe", 1, ""), ("pe_redis", 1, ""), ("pe_redis", -1, "gzip JSON"), ("portA_pe", -1, ""), ("api_port", -1, "")],
             text="Out through VNet integration to the Redis private endpoint: GET {asa}:v1:summary (gzip JSON). The app keeps it for 60 seconds."),
        dict(title="Render the views", focus=["browser"], src="API",
             hops=[("br_api", -1, "JSON")],
             text="The API returns the compressed JSON and the map, service matrix, VM finder and Managed Redis views render in the browser."),
    ]),
    dict(id="signedin", name="Signed-in read", short="Signed in", tagline="contoso.day accounts, Microsoft Entra ID", steps=[
        dict(title="Sign in", src="AUTHCODE",
             hops=[("br_entra", 1, "authorize · PKCE"), ("br_entra", -1, "code")],
             text="Authorization code flow with PKCE against the contoso.day tenant (domain_hint=contoso.day). PKCE is required for single-page apps; no secret lives in the page."),
        dict(title="Redeem the code", src="AUTHCODE",
             hops=[("br_entra", 1, "code + verifier"), ("br_entra", -1, "access token")],
             text="The SPA redirect URI lets the browser call the token endpoint (CORS). It returns an access token for Availability.Read; refresh tokens for SPAs last 24 hours."),
        dict(title="Call the API with the token", src="CORS",
             hops=[("br_api", 1, "Bearer token")],
             text="GET /api/summary with Authorization: Bearer <access token>, from the allowed origin https://ibranibeny.github.io."),
        dict(title="Validate the token", src="ACCESS_TOKENS",
             hops=[("api_entra", 1, "JWKS"), ("api_entra", -1, "signing keys")],
             text="Signature against the tenant's signing keys (jwks_uri, cached 6 h), then issuer, audience, tenant, the Availability.Read scope, the calling app (azp) and a contoso.day member account."),
        dict(title="Token for Redis", src="REDIS_ENTRA",
             hops=[("api_mi", 1, "token for redis.azure.com"), ("mi_entra", 1, ""), ("mi_entra", -1, "Entra token"), ("api_mi", -1, "")],
             text="The API's managed identity gets a token for Redis; the user's token is never passed on to Azure resources."),
        dict(title="Read the snapshot privately", src="REDIS_PL",
             hops=[("api_port", 1, "GET summary"), ("portA_pe", 1, ""), ("pe_redis", 1, ""), ("pe_redis", -1, "gzip JSON"), ("portA_pe", -1, ""), ("api_port", -1, "")],
             text="Same private path as guests: VNet integration, private endpoint, TLS port 10000."),
        dict(title="Full view", focus=["browser"], src="API",
             hops=[("br_api", -1, "JSON")],
             text="The JSON goes back to the browser, including the collector's run details that guests don't see."),
    ]),
    dict(id="deploy", name="Deploy & publish", short="Deploy", tagline="Cloud Shell, Bicep, package deployment, GitHub Pages", steps=[
        dict(title="App registrations", src="AUTHCODE",
             hops=[("sh_entra", 1, "Microsoft Graph"), ("sh_entra", -1, "app IDs")],
             text="scripts/entra-apps.sh creates or updates the dashboard app (SPA redirect URIs) and the API app (scope Availability.Read) through Microsoft Graph."),
        dict(title="Infrastructure as code", src="FLEX_HOWTO",
             hops=[("sh_arm", 1, "main.bicep"), ("sh_arm", -1, "Succeeded")],
             text="az deployment group create runs infra/main.bicep: VNet, subnets, private endpoints and DNS zones, Managed Redis, storage, identities, roles and both Flex Consumption apps, created one after the other because they share snet-functions."),
        dict(title="Deploy the packages", src="DEPLOY",
             hops=[("sh_col", 1, "collector.zip"), ("sh_api", 1, "api.zip")],
             text="az functionapp deployment source config-zip uploads each app as a Flex Consumption package deployment: the collector (52 MB, with the Azure CLI) and the API (7 MB)."),
        dict(title="Load from private storage", src="APP_SETTINGS",
             hops=[("col_port", 1, "package"), ("portC_pe", 1, ""), ("pe_sto", 1, ""), ("api_port", 1, "package"), ("portA_pe", 1, ""), ("pe_sto", 1, "")],
             text="Packages sit in each app's blob deployment container. The apps reach it, and their host storage, through the storage private endpoints with their managed identity; shared keys are off."),
        dict(title="Publish the dashboard", src="PAGES",
             hops=[("repo_pages", 1, "commit to main /docs")],
             text="A commit to main /docs publishes the site with GitHub Pages (deploy from a branch)."),
        dict(title="First collection", focus=["collector"], src="RUN",
             hops=[("sh_col", 1, "run now")],
             text="scripts/run-collector.sh calls the collector's admin endpoint to run the timer function once; after that the schedule takes over."),
    ]),
]
