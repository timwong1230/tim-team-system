"""Shared constants for TIM TEAM system."""

INACTIVE_MEMBERS = ["Wilson", "Catherine", "Maggie"]

MDRT_TARGET = 512_800
Q1_TARGET = 88_000
WEEKLY_MIN_ACTS = 3
WEEKLY_PENALTY = 100

ACTIVITY_TYPES = [
    "見面 (1分)",
    "傾保險 (2分)",
    "傾招募 (2分)",
    "新人報考試 (3分)",
    "簽單 (5分)",
    "新人出code (8分)",
]

TEMPLATE_SALES = (
    "【客戶資料】\n"
    "Name: \n"
    "講左3Q? 有咩feedback? \n"
    "Fact Find 重點: \n\n"
    "【面談內容】\n"
    "Sell左咩Plan? \n"
    "客戶反應/抗拒點: \n\n"
    "【下一步】\n"
    "下次見面日期: \n"
    "Action Items: "
)

TEMPLATE_RECRUIT = (
    "【準增員資料】\n"
    "Name: \n"
    "背景/現職: \n"
    "對現狀不滿 (Pain Points): \n"
    "對行業最大顧慮: \n\n"
    "【面談內容】\n"
    "Sell 左咩 Vision?: \n"
    "有無邀請去Team Dinner / Recruitment Talk? \n\n"
    "【下一步】\n"
    "下次跟進日期: \n"
    "Action Items: "
)

TEMPLATE_NEWBIE = (
    "【新人跟進】\n"
    "新人 Name: \n"
    "今日進度 (考牌/Training/出Code): \n"
    "遇到咩困難?: \n"
    "Leader 俾左咩建議?: \n\n"
    "【下一步】\n"
    "Target: \n"
    "下次 Review 日期: "
)

AMMO_CATEGORIES = [
    "行為金融學 (理智漏洞)",
    "醫療理賠 (危機感)",
    "財富傳承 (家族案例)",
    "資產配置 (觀念導正)",
    "市場熱話 / 政策解讀",
]

# Common FWD Iris / production-report header aliases (case-insensitive match)
IRIS_AGENT_ALIASES = [
    "agent name",
    "agent",
    "advisor name",
    "advisor",
    "consultant",
    "顧問姓名",
    "代理人姓名",
    "代理人",
    "姓名",
    "name",
    "member name",
    "producer name",
]

IRIS_CODE_ALIASES = [
    "agent code",
    "agent no",
    "agent number",
    "advisor code",
    "代理人編號",
    "顧問編號",
    "code",
    "staff code",
    "producer code",
]

# Prefer Monthly Completion — NEVER Monthly Submission
IRIS_MONTHLY_COMPLETION_ALIASES = [
    "monthly completion",
    "month completion",
    "mtd completion",
    "completion monthly",
    "monthly complete",
    "本月完成",
    "當月完成",
    "每月完成",
    "月度完成",
    "本月 completion",
    "當月 completion",
]

# YTD Completion → Team FYC / yearly MDRT progress
IRIS_YTD_COMPLETION_ALIASES = [
    "ytd completion",
    "year to date completion",
    "ytd complete",
    "yearly completion",
    "ytd",
    "year-to-date completion",
    "累積完成",
    "全年完成",
    "年累完成",
    "ytd 完成",
]

# Fallback FYC aliases (still reject submission columns)
IRIS_FYC_ALIASES = [
    "fyc",
    "first year commission",
    "fy commission",
    "首年佣金",
    "佣金",
    "commission",
    "ape",
    "anp",
    "fyp",
    "production",
    "業績",
    "amount",
    "total fyc",
    "completion",
]

# Columns that must not be used as FYC / completion
IRIS_FYC_REJECT_SUBSTR = [
    "submission",
    "submit",
    "submitted",
    "呈報",
    "提交",
    "報送",
]

IRIS_MONTH_ALIASES = [
    "month",
    "production month",
    "period",
    "業績月份",
    "月份",
    "yr mo",
    "year month",
]

# Special month key storing Iris YTD Completion per agent
IRIS_YTD_MONTH_KEY = "YTD"

SHEET_SCHEMAS = {
    "users": ["username", "password", "role", "team", "recruit", "avatar", "last_read"],
    "monthly_fyc": ["id", "username", "month", "amount", "source", "updated_at"],
    "activities": ["id", "username", "date", "type", "points", "note", "timestamp"],
    "story_ammo": [
        "id",
        "username",
        "date",
        "category",
        "title",
        "knowledge",
        "story_context",
        "nightmare",
        "dream",
        "scenario",
        "timestamp",
    ],
    "iris_agent_map": ["iris_name", "iris_code", "username", "notes"],
    "iris_sync_log": [
        "id",
        "synced_at",
        "synced_by",
        "month",
        "filename",
        "rows_total",
        "rows_matched",
        "rows_updated",
        "status",
        "note",
    ],
    "system_settings": ["id", "key", "value", "updated_at"],
}
