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
    "【Fact find background】\n"
    "Name: \n\n"
    "1. 性格：\n\n"
    "2. 工作情況（職業／人工／年資）：\n\n"
    "3. 家庭現況（家庭人物關係圖）：\n\n"
    "4. 興趣：\n\n"
    "5. 人生最大經歷／轉捩點：\n\n"
    "6. 未來目標／想做的事情：\n\n"
    "7. 未來關心／擔心的事情：\n\n"
    "8. ⚠️ prepare 切入主題角度 — 用咩切入？：\n\n"
    "9. 已買保險？（病歷紀錄）：\n\n"
    "10. 邊間公司：\n\n"
    "11. 同 agent 關係：\n\n"
    "12. 落咗咩 sales concept：\n\n"
    "13. 點跟進客人 follow up：\n\n"
    "14. 經過今日之後嘅了解，你哋彼此嘅熟悉程度：\n\n"
    "15. ⚠️ 約 next appointment／活動：日子："
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

# Prefer MTD Completion FYC — NEVER MTD Submission / MTD_Sub_FYC
# Daily production report column: MTD_Comp_FYC (also MTD-COMPLETION)
IRIS_MONTHLY_COMPLETION_ALIASES = [
    "mtd comp fyc",
    "mtd_comp_fyc",
    "mtdcompfyc",
    "mtd comp",
    "mtd_comp",
    "comp fyc",
    "mtd-completion",
    "mtd completion",
    "mtd_completion",
    "mtd completion fyc",
    "mtd-completion fyc",
    "fyc mtd completion",
    "mtd fyc completion",
    "monthly completion",
    "month completion",
    "completion monthly",
    "monthly complete",
    "本月完成",
    "當月完成",
    "每月完成",
    "月度完成",
    "本月 completion",
    "當月 completion",
]

# MDRT Progress Report: Total Credit eligible for MDRT
MDRT_CREDIT_ALIASES = [
    "total credit eligible for mdrt",
    "credit eligible for mdrt",
    "total credit eligible",
    "eligible for mdrt",
    "mdrt credit",
    "total mdrt credit",
    "mdrt total credit",
    "total credit",
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
    "mtd sub fyc",
    "mtd_sub_fyc",
    "mtd sub",
    "mtd_sub",
    "sub fyc",
    "sub_fyc",
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

# Special month key: 2027 MDRT temporary progress (plan bonus + other credit)
MDRT_PROGRESS_MONTH_KEY = "MDRT_2027"

# Dashboard Team SC (manual override stored in system_settings)
TEAM_SC_SETTING_KEY = "team_sc"

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
    "quarterly_offers": [
        "id",
        "quarter",
        "kind",
        "title",
        "detail",
        "note",
        "sort",
        "updated_at",
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
    "common_forms": [
        "id",
        "title",
        "category",
        "filename",
        "mime",
        "drive_file_id",
        "size_bytes",
        "uploaded_by",
        "uploaded_at",
        "note",
    ],
}
