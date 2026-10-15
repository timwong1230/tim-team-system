"""
常見疾病核保指引 — structured from Medical Manual v2.0 (Jan 2020).

Outcomes are reference only; FWD retains final underwriting authority.
"""

from __future__ import annotations

DISCLAIMER_ZH = (
    "本功能只供內部參考，並非最終核保決定。"
    "FWD 會按客人整體健康狀況／保額要求額外資料或身體檢查，並保留一切最終決定權。"
    "嚴禁向公眾或客戶分發原文核保指引。除非另有說明，資料一般適用於成年人。"
)

# Shorthand outcome strings aligned to the manual
STD = "標準保費"
SUB = "視乎嚴重程度或會加保費"
SUB50 = "+50% 起或會加保費"
EXC = "不保事項"
EXC50 = "不保事項／+50% 起"
POST = "延遲受保"
DEC = "拒絕受保"
IND = "個別考慮"
STD50_POST = "+50% 起至延遲受保"
EXC_POST = "不保事項／+50% 起至延遲受保"
STD_MAY_SUB = "標準保費（視乎嚴重程度或會加保費）"


def _sc(sid: str, label: str, match: dict, life, ci, medical, accident, cancer, note: str = "") -> dict:
    return {
        "id": sid,
        "label_zh": label,
        "match": match,
        "note": note,
        "outcomes": {
            "life": life,
            "ci": ci,
            "medical": medical,
            "accident": accident,
            "cancer": cancer,
        },
    }


def _q(qid: str, prompt: str, options: list[tuple[str, str]]) -> dict:
    return {
        "id": qid,
        "prompt": prompt,
        "type": "choice",
        "options": [{"value": v, "label": lab} for v, lab in options],
    }


DISEASES: list[dict] = [
    {
        "id": "anaemia",
        "name_zh": "貧血",
        "name_en": "Anaemia",
        "keywords": ["貧血", "缺鐵", "anaemia", "anemia"],
        "description_zh": "貧血是由於缺乏紅細胞引起。最常見為缺鐵性貧血；了解根本原因非常重要。",
        "extra_reqs": ["可能需要：驗血 — 血全像（CBC）", "可能需要：遞交檢查報告"],
        "questions": [
            _q("type", "貧血類型？", [("iron", "缺鐵性貧血"), ("other", "其他貧血"), ("unknown", "其他／未查清")]),
            _q("years", "距離情況大概幾耐？", [("gt2", "超過 2 年"), ("le2", "2 年或以內")]),
            _q(
                "status",
                "而家狀況？",
                [
                    ("clear", "無症狀、無需藥物／治療、無需覆診（完全康復）"),
                    ("active", "有服藥／治療及／或定期覆診"),
                    ("uncertain", "狀況不確定／未經調查"),
                ],
            ),
            _q("complication", "有冇併發症（由其他病引起或導致其他病）？", [("no", "沒有"), ("yes", "有")]),
        ],
        "scenarios": [
            _sc("iron_gt2_clear", "缺鐵性貧血 > 2 年：無症狀、無需治療、無需覆診", {"type": "iron", "years": "gt2", "status": "clear"}, STD, STD, STD, STD, STD),
            _sc("iron_le2_active", "缺鐵性貧血 ≤ 2 年：有服藥／治療及／或定期覆診", {"type": "iron", "years": "le2", "status": "active"}, SUB, STD50_POST, EXC_POST, STD, STD),
            _sc("other_le2_active", "其他貧血 ≤ 2 年：有服藥／治療及／或定期覆診", {"type": "other", "years": "le2", "status": "active"}, STD50_POST, STD50_POST, "不保事項至拒絕受保", STD, "標準保費（揀易保轉換個別考慮）"),
            _sc("other_gt2_clear", "其他貧血 > 2 年：無症狀、無需治療、無需覆診", {"type": "other", "years": "gt2", "status": "clear"}, STD, STD, STD, STD, STD),
            _sc("uncertain", "其他；或未經調查，狀況不確定", {"status": "uncertain"}, IND, IND, IND, IND, IND),
            _sc("unknown_any", "類型未確定", {"type": "unknown"}, IND, IND, IND, IND, IND),
        ],
    },
    {
        "id": "anxiety",
        "name_zh": "焦慮／抑鬱／情緒障礙",
        "name_en": "Anxiety / Depression / Mood Disorders",
        "keywords": ["焦慮", "抑鬱", "情緒", "depression", "anxiety", "壓力"],
        "description_zh": "包括焦慮、抑鬱、情緒障礙、壓力及適應障礙等。需了解治療、症狀與對日常／工作影響。",
        "extra_reqs": ["可能需要：覆診卡副本及授權書", "可能需要：主診醫生報告（PMA）"],
        "questions": [
            _q("type", "疾病類型？", [("anxiety", "焦慮"), ("depression", "抑鬱"), ("mood", "情緒障礙"), ("stress", "壓力／適應障礙"), ("other", "其他")]),
            _q("years", "距離完全康復大概幾耐？", [("gt5", "超過 5 年"), ("le5", "5 年或以內／仍在處理")]),
            _q(
                "status",
                "而家狀況？",
                [
                    ("clear", "完全康復：無需治療、無症狀、對工作／日常無損害"),
                    ("active", "仍有症狀及／或治療中"),
                ],
            ),
            _q("impairment", "有冇損害日常活動（例如避免社交）？", [("no", "沒有"), ("yes", "有")]),
        ],
        "scenarios": [
            _sc("gt5_clear", "> 5 年：完全康復、無需治療、無症狀、無損害", {"years": "gt5", "status": "clear"}, SUB, SUB, EXC_POST, STD, STD),
            _sc("le5_active", "≤ 5 年：有症狀及／或治療中", {"years": "le5", "status": "active"}, IND, IND, POST, STD, "標準保費（揀易保無轉換選項）"),
        ],
    },
    {
        "id": "arthritis",
        "name_zh": "關節炎（退化性／骨關節炎）",
        "name_en": "Arthritis, Degenerative or Osteoarthritis",
        "keywords": ["關節炎", "骨關節", "arthritis", "退化"],
        "description_zh": "退化性或骨關節炎。需了解部位、治療、活動受限程度。",
        "extra_reqs": ["可能需要：相關檢查報告或醫生報告"],
        "questions": [
            _q("years", "發病／治療情況？", [("mild", "輕微、活動影響少"), ("active", "需定期治療／明顯影響活動"), ("severe", "嚴重或手術後未穩")]),
            _q("surgery", "有冇做過相關手術？", [("no", "沒有"), ("yes", "有")]),
        ],
        "scenarios": [
            _sc("mild", "輕微退化性關節炎，影響少", {"years": "mild"}, STD_MAY_SUB, STD_MAY_SUB, EXC, STD, STD),
            _sc("active", "需定期治療或活動明顯受限", {"years": "active"}, SUB, SUB, EXC_POST, STD, STD),
            _sc("severe", "嚴重／手術後狀況未穩", {"years": "severe"}, IND, IND, POST, STD, IND),
        ],
    },
    {
        "id": "asthma",
        "name_zh": "哮喘",
        "name_en": "Asthma",
        "keywords": ["哮喘", "asthma", "氣喘"],
        "description_zh": "哮喘可影響呼吸功能。需了解病發頻率、藥物及吸煙史。",
        "extra_reqs": ["吸煙人士通常額外 +50%", "可能需要：肺功能／病歷資料"],
        "questions": [
            _q("age_group", "受保人年齡組別？", [("child", "少於 2 歲（已知哮喘）"), ("adult", "2 歲或以上／成人")]),
            _q("years", "最近病發／用藥？", [("gt2", "超過 2 年無病發、無症狀"), ("le2", "≤ 2 年有病發及有藥物治療")]),
            _q("smoker", "有冇吸煙？", [("no", "沒有"), ("yes", "有（通常額外 +50%）")]),
        ],
        "scenarios": [
            _sc("child", "< 2 歲；已知哮喘", {"age_group": "child"}, POST, POST, POST, STD, "標準保費（揀易保無轉換選項）"),
            _sc("gt2_clear", "> 2 年：沒有病發及沒有症狀", {"age_group": "adult", "years": "gt2"}, STD, STD, STD, STD, STD),
            _sc("le2_active", "≤ 2 年：有病發及有藥物治療", {"age_group": "adult", "years": "le2"}, STD_MAY_SUB, STD_MAY_SUB, EXC, STD, "標準保費（揀易保轉換個別考慮）"),
        ],
    },
    {
        "id": "back_pain",
        "name_zh": "背痛",
        "name_en": "Back Pain",
        "keywords": ["背痛", "腰椎", "back pain", "脊骨"],
        "description_zh": "背痛成因多樣。需了解持續時間、治療、手術及對工作影響。",
        "extra_reqs": ["可能需要：影像報告或醫生報告"],
        "questions": [
            _q("status", "而家狀況？", [("resolved", "已痊癒／偶發、無持續治療"), ("chronic", "慢性／定期治療"), ("surgery", "曾手術或神經受壓")]),
            _q("work", "有冇因此請長假或影響工作？", [("no", "沒有"), ("yes", "有")]),
        ],
        "scenarios": [
            _sc("resolved", "已紓緩／偶發，無持續治療", {"status": "resolved"}, STD, STD, EXC, STD, STD),
            _sc("chronic", "慢性背痛、定期治療", {"status": "chronic"}, SUB, SUB, EXC_POST, STD, STD),
            _sc("surgery", "曾手術或較嚴重神經症狀", {"status": "surgery"}, IND, IND, POST, STD, IND),
        ],
    },
    {
        "id": "breast_benign",
        "name_zh": "乳房良性疾病／腫塊（女性）",
        "name_en": "Breast Benign Condition / Lump (Female)",
        "keywords": ["乳房", "乳腺", "breast", "腫塊", "纖維瘤"],
        "description_zh": "乳房良性情況／腫塊。需確認良性診斷、手術及跟進。",
        "extra_reqs": ["可能需要：病理／超聲波／乳房造影報告"],
        "questions": [
            _q("status", "診斷與跟進？", [("benign_clear", "已確認良性、完成治療、無需再跟進"), ("monitor", "良性但需定期監察"), ("uncertain", "未完全排除惡性／仍在調查")]),
        ],
        "scenarios": [
            _sc("clear", "已確認良性並完成跟進", {"status": "benign_clear"}, STD, STD, EXC, STD, STD),
            _sc("monitor", "良性但需定期監察", {"status": "monitor"}, STD_MAY_SUB, SUB, EXC, STD, SUB),
            _sc("uncertain", "未排除惡性或仍在調查", {"status": "uncertain"}, POST, POST, POST, STD, POST),
        ],
    },
    {
        "id": "build",
        "name_zh": "體型（超重及體重不足）",
        "name_en": "Build (Overweight & Underweight)",
        "keywords": ["肥胖", "超重", "體重", "bmi", "build", "過瘦"],
        "description_zh": "以身高體重／BMI 評估。極端體型或伴其他風險時核保結果會較嚴。",
        "extra_reqs": ["請準備身高、體重；或會要求驗身"],
        "questions": [
            _q("build", "體型屬於？", [("normal", "正常範圍"), ("over", "超重"), ("obese", "明顯肥胖"), ("under", "體重明顯不足")]),
            _q("other_risk", "有冇同時糖尿病／高血壓等風險？", [("no", "沒有"), ("yes", "有")]),
        ],
        "scenarios": [
            _sc("normal", "體型正常", {"build": "normal"}, STD, STD, STD, STD, STD),
            _sc("over", "超重（無其他重大風險）", {"build": "over", "other_risk": "no"}, STD_MAY_SUB, STD_MAY_SUB, STD_MAY_SUB, STD, STD),
            _sc("obese", "明顯肥胖", {"build": "obese"}, SUB, SUB, SUB, STD, STD),
            _sc("under", "體重明顯不足", {"build": "under"}, IND, IND, IND, STD, IND),
            _sc("over_risk", "超重並有其他風險因素", {"other_risk": "yes"}, IND, IND, IND, STD, IND),
        ],
    },
    {
        "id": "cataract",
        "name_zh": "白內障",
        "name_en": "Cataract",
        "keywords": ["白內障", "cataract", "眼睛"],
        "description_zh": "白內障常見於年長人士。手術前後狀況影響醫療核保。",
        "extra_reqs": ["可能需要：眼科報告"],
        "questions": [
            _q("status", "狀況？", [("done", "已做手術並康復"), ("pending", "未做手術／待手術"), ("comp", "有併發症")]),
        ],
        "scenarios": [
            _sc("done", "已手術並康復", {"status": "done"}, STD, STD, EXC, STD, STD),
            _sc("pending", "未手術／待手術", {"status": "pending"}, STD, STD, EXC_POST, STD, STD),
            _sc("comp", "有併發症", {"status": "comp"}, IND, IND, POST, STD, IND),
        ],
    },
    {
        "id": "cin",
        "name_zh": "子宮頸上皮內贅瘤（CIN）",
        "name_en": "Cervical Intraepithelial Neoplasia (CIN)",
        "keywords": ["cin", "子宮頸", "pap", "hpv"],
        "description_zh": "CIN 分級與治療後跟進結果影響危疾／癌症相關核保。",
        "extra_reqs": ["可能需要：病理及覆查報告"],
        "questions": [
            _q("grade", "CIN 級別／情況？", [("low_clear", "低度／已治療且覆查正常"), ("high", "高度病變或持續異常"), ("active", "仍在治療／未完成跟進")]),
        ],
        "scenarios": [
            _sc("low_clear", "低度病變已治療，覆查正常", {"grade": "low_clear"}, STD, STD, EXC, STD, STD),
            _sc("high", "高度病變或持續異常", {"grade": "high"}, SUB, SUB, EXC_POST, STD, SUB),
            _sc("active", "仍在治療／未完成跟進", {"grade": "active"}, POST, POST, POST, STD, POST),
        ],
    },
    {
        "id": "chest_pain",
        "name_zh": "胸痛（非心臟性）",
        "name_en": "Chest Pain, non-cardiac",
        "keywords": ["胸痛", "chest pain", "心臟"],
        "description_zh": "需排除心臟問題。已確認非心臟性且康復，與仍在調查，結果差很遠。",
        "extra_reqs": ["可能需要：心電圖／心臟科報告"],
        "questions": [
            _q("status", "調查結果？", [("noncardiac_clear", "已確認非心臟性並康復"), ("investigating", "仍在調查／未排除心臟"), ("cardiac_suspected", "懷疑或確診心臟相關")]),
        ],
        "scenarios": [
            _sc("clear", "已確認非心臟性並康復", {"status": "noncardiac_clear"}, STD, STD, STD, STD, STD),
            _sc("invest", "仍在調查", {"status": "investigating"}, POST, POST, POST, STD, POST),
            _sc("cardiac", "懷疑／確診心臟相關", {"status": "cardiac_suspected"}, IND, IND, IND, STD, IND),
        ],
    },
    {
        "id": "colorectal_polyp",
        "name_zh": "大腸直腸息肉",
        "name_en": "Colorectal Polyp",
        "keywords": ["息肉", "大腸", "直腸", "polyp", "结肠"],
        "description_zh": "息肉數目、病理性質及切除後跟進影響核保。",
        "extra_reqs": ["可能需要：大腸鏡及病理報告"],
        "questions": [
            _q("status", "情況？", [("benign_removed", "良性、已切除、跟進正常"), ("multiple", "多發或需密切監察"), ("malignant_risk", "病理高風險／未清")]),
        ],
        "scenarios": [
            _sc("benign", "良性已切除，跟進正常", {"status": "benign_removed"}, STD, STD, EXC, STD, STD),
            _sc("multiple", "多發或需密切監察", {"status": "multiple"}, SUB, SUB, EXC, STD, SUB),
            _sc("risk", "高風險病理或未處理妥", {"status": "malignant_risk"}, POST, POST, POST, STD, POST),
        ],
    },
    {
        "id": "diabetes",
        "name_zh": "糖尿病／妊娠糖尿病",
        "name_en": "Diabetes Mellitus / Gestational Diabetes Mellitus",
        "keywords": ["糖尿病", "diabetes", "血糖", "妊娠糖尿", "gdm"],
        "description_zh": "需區分一／二型與妊娠糖尿病，以及控制情況與併發症。",
        "extra_reqs": ["可能需要：血糖／HbA1c、尿液及併發症相關檢查"],
        "questions": [
            _q("dtype", "類型？", [("t2_good", "糖尿病（控制良好、無併發症）"), ("t2_poor", "糖尿病（控制不良及／或有併發症／其他風險）"), ("other", "其他複雜情況"), ("gdm_clear", "妊娠糖尿病：分娩後血糖正常、完全恢復")]),
        ],
        "scenarios": [
            _sc("good", "控制良好；沒有其他風險因素／併發症", {"dtype": "t2_good"}, SUB50, SUB50, IND, STD, "標準保費（揀易保無轉換選項）"),
            _sc("poor", "控制不良；及／或有其他風險／併發症", {"dtype": "t2_poor"}, IND, SUB50, IND, STD, "標準保費（揀易保無轉換選項）"),
            _sc("other", "其他", {"dtype": "other"}, IND, DEC, DEC, STD, IND),
            _sc("gdm", "妊娠糖尿病：分娩後血糖恢復正常、無併發症", {"dtype": "gdm_clear"}, STD, STD, STD, STD, STD),
        ],
    },
    {
        "id": "family_history",
        "name_zh": "家族病史",
        "name_en": "Family History Disorder",
        "keywords": ["家族", "family", "遺傳", "病史"],
        "description_zh": "直系親屬重大疾病史或影響危疾／癌症評估，視乎疾病種類與發病年齡。",
        "extra_reqs": ["請清楚記錄親屬關係、疾病及發病年齡"],
        "questions": [
            _q("impact", "家族病史性質？", [("minor", "一般／較常見、發病年齡較高"), ("major", "直系親屬早發危疾／癌症等重大病史"), ("genetic", "已知遺傳性疾病相關")]),
        ],
        "scenarios": [
            _sc("minor", "家族病史影響較低", {"impact": "minor"}, STD, STD, STD, STD, STD),
            _sc("major", "直系親屬重大／早發病史", {"impact": "major"}, STD_MAY_SUB, SUB, STD, STD, SUB),
            _sc("genetic", "已知遺傳相關風險", {"impact": "genetic"}, IND, IND, IND, STD, IND),
        ],
    },
    {
        "id": "fatty_liver",
        "name_zh": "脂肪肝",
        "name_en": "Fatty Liver",
        "keywords": ["脂肪肝", "fatty liver", "肝"],
        "description_zh": "脂肪肝常見。肝功能是否正常、有否治療／覆診是關鍵。",
        "extra_reqs": ["可能需要：近期肝功能測試報告"],
        "questions": [
            _q(
                "status",
                "而家狀況？",
                [
                    ("clear_lft", "無症狀、從未藥物治療、無需覆診，且 ≤12 個月肝功能正常"),
                    ("abnormal_lft", "無症狀、無藥物；但肝功能異常或近 12 個月未做"),
                    ("treated", "曾經或正接受藥物／治療及／或定期覆診"),
                ],
            ),
        ],
        "scenarios": [
            _sc("clear", "無症狀、無治療、無需覆診，≤12 個月肝功能正常", {"status": "clear_lft"}, STD, STD, STD, STD, STD),
            _sc("abn", "無症狀、無治療；肝功能異常或未做", {"status": "abnormal_lft"}, "視乎肝功能或會加保費", STD_MAY_SUB, "不保事項／視乎肝功能加保費", STD, "視乎肝功能或會加保費"),
            _sc("treated", "曾／正接受藥物或定期覆診", {"status": "treated"}, IND, IND, IND, STD, IND),
        ],
    },
    {
        "id": "gastritis",
        "name_zh": "胃炎",
        "name_en": "Gastritis",
        "keywords": ["胃炎", "胃酸", "gastritis", "幽門"],
        "description_zh": "胃炎多可控制。潰瘍、出血或未查清原因需更審慎。",
        "extra_reqs": ["可能需要：胃鏡報告"],
        "questions": [
            _q("status", "狀況？", [("mild", "輕微／已受控、無併發症"), ("ulcer", "潰瘍／曾出血"), ("active", "仍頻密病發或未完成檢查")]),
        ],
        "scenarios": [
            _sc("mild", "輕微已受控", {"status": "mild"}, STD, STD, EXC, STD, STD),
            _sc("ulcer", "潰瘍或曾出血", {"status": "ulcer"}, SUB, SUB, EXC_POST, STD, STD),
            _sc("active", "仍頻密病發／未查清", {"status": "active"}, IND, IND, POST, STD, IND),
        ],
    },
    {
        "id": "g6pd",
        "name_zh": "G6PD 缺乏症",
        "name_en": "G6PD Deficiency",
        "keywords": ["g6pd", "蠶豆", "葡萄糖"],
        "description_zh": "遺傳性酵素缺乏。多數無症狀，但需避免誘發藥物／食物。",
        "extra_reqs": ["記錄有否溶血發作史"],
        "questions": [
            _q("status", "有冇溶血發作或相關併發症？", [("none", "無發作、無併發症"), ("history", "曾有發作但已穩"), ("recent", "近期發作／未穩")]),
        ],
        "scenarios": [
            _sc("none", "無發作、無併發症", {"status": "none"}, STD, STD, STD, STD, STD),
            _sc("history", "曾有發作但已穩定", {"status": "history"}, STD_MAY_SUB, STD_MAY_SUB, EXC, STD, STD),
            _sc("recent", "近期發作／未穩", {"status": "recent"}, POST, POST, POST, STD, POST),
        ],
    },
    {
        "id": "gout",
        "name_zh": "痛風",
        "name_en": "Gout",
        "keywords": ["痛風", "gout", "尿酸"],
        "description_zh": "痛風與尿酸有關。發作頻率、藥物及腎併發症影響評估。",
        "extra_reqs": ["可能需要：尿酸／腎功能報告"],
        "questions": [
            _q("status", "狀況？", [("rare", "偶發、控制良好"), ("frequent", "頻密發作或長期藥物"), ("comp", "有腎／關節併發症")]),
        ],
        "scenarios": [
            _sc("rare", "偶發、控制良好", {"status": "rare"}, STD, STD, EXC, STD, STD),
            _sc("freq", "頻密發作或長期藥物", {"status": "frequent"}, SUB, SUB, EXC, STD, STD),
            _sc("comp", "有併發症", {"status": "comp"}, IND, IND, EXC_POST, STD, IND),
        ],
    },
    {
        "id": "haemorrhoid",
        "name_zh": "痔瘡",
        "name_en": "Haemorrhoid",
        "keywords": ["痔瘡", "haemorrhoid", "hemorrhoid"],
        "description_zh": "痔瘡常見。手術後康復與持續出血情況影響醫療核保。",
        "extra_reqs": [],
        "questions": [
            _q("status", "狀況？", [("mild", "輕微／已處理"), ("surgery", "曾手術並康復"), ("active", "持續出血或未處理")]),
        ],
        "scenarios": [
            _sc("mild", "輕微／已處理", {"status": "mild"}, STD, STD, EXC, STD, STD),
            _sc("surgery", "曾手術並康復", {"status": "surgery"}, STD, STD, EXC, STD, STD),
            _sc("active", "持續症狀", {"status": "active"}, STD, STD, EXC_POST, STD, STD),
        ],
    },
    {
        "id": "hepatitis",
        "name_zh": "肝炎",
        "name_en": "Hepatitis",
        "keywords": ["肝炎", "hepatitis", "乙肝", "甲肝", "hbsag"],
        "description_zh": "需分甲型／乙型及帶菌狀態。肝功能與抗原結果很關鍵。",
        "extra_reqs": ["可能需要：肝功能、乙肝抗原／病毒量報告"],
        "questions": [
            _q(
                "htype",
                "類型與狀況？",
                [
                    ("a_active", "甲型肝炎 — 未康復"),
                    ("a_clear", "甲型肝炎 — 完全康復"),
                    ("b_carrier_good", "乙肝帶菌 — 無需治療／覆診、肝功能正常、HBeAg 陰性"),
                    ("b_carrier_bad", "乙肝帶菌 — 肝功能異常及／或 HBeAg 陽性"),
                    ("b_recover_le6", "乙肝（非帶菌）完全康復 ≤ 6 個月"),
                    ("b_recover_gt6", "乙肝（非帶菌）完全康復 > 6 個月"),
                    ("other", "其他／未明"),
                ],
            ),
        ],
        "scenarios": [
            _sc("a_active", "甲型肝炎 — 未康復", {"htype": "a_active"}, POST, POST, POST, STD, POST),
            _sc("a_clear", "甲型肝炎 — 完全康復", {"htype": "a_clear"}, STD, STD, STD, STD, STD),
            _sc("b_good", "乙肝帶菌 — 無需治療、肝功能正常、HBeAg 陰性", {"htype": "b_carrier_good"}, STD, STD, STD, STD, STD),
            _sc("b_bad", "乙肝帶菌 — 肝功能異常及／或 HBeAg 陽性", {"htype": "b_carrier_bad"}, SUB50, SUB50, EXC50, STD, SUB50),
            _sc("b_le6", "乙肝完全康復 ≤ 6 個月", {"htype": "b_recover_le6"}, POST, POST, POST, STD, POST),
            _sc("b_gt6", "乙肝完全康復 > 6 個月", {"htype": "b_recover_gt6"}, STD, STD, STD, STD, STD),
            _sc("other", "其他／未明", {"htype": "other"}, IND, IND, IND, STD, IND),
        ],
    },
    {
        "id": "hypercholesterolemia",
        "name_zh": "高膽固醇血症",
        "name_en": "Hypercholesterolemia",
        "keywords": ["膽固醇", "血脂", "cholesterol", "lipid"],
        "description_zh": "視乎指數、藥物控制及有否其他心血管風險。",
        "extra_reqs": ["可能需要：近期血脂報告"],
        "questions": [
            _q("status", "控制情況？", [("diet", "飲食控制、指數理想、無其他風險"), ("med_good", "藥物控制良好"), ("poor", "控制欠佳或有其他心血管風險")]),
        ],
        "scenarios": [
            _sc("diet", "飲食控制良好、無其他風險", {"status": "diet"}, STD, STD, STD, STD, STD),
            _sc("med", "藥物控制良好", {"status": "med_good"}, STD_MAY_SUB, STD_MAY_SUB, STD_MAY_SUB, STD, STD),
            _sc("poor", "控制欠佳或合併其他風險", {"status": "poor"}, SUB, SUB, SUB, STD, STD),
        ],
    },
    {
        "id": "hypertension",
        "name_zh": "高血壓",
        "name_en": "Hypertension",
        "keywords": ["高血壓", "血壓", "hypertension", "bp"],
        "description_zh": "關鍵係血壓讀數、有否服藥／覆診、控制是否良好及有否併發症。",
        "extra_reqs": ["請記錄最近血壓讀數；可能需要驗身"],
        "questions": [
            _q(
                "status",
                "控制情況？",
                [
                    ("no_med", "醫生無要求服藥／定期覆診；上次血壓理想"),
                    ("med_good", "服藥及覆診、控制良好、無併發症、近 6 個月無加重藥物"),
                    ("high", "正接受藥物／覆診；及／或血壓 > 140/90"),
                    ("other", "其他（有併發症或不穩）"),
                ],
            ),
        ],
        "scenarios": [
            _sc("no_med", "無需服藥／定期覆診；血壓理想", {"status": "no_med"}, STD, STD, STD, STD, STD),
            _sc("med_good", "服藥控制良好、無併發症", {"status": "med_good"}, STD, STD, STD, STD, STD),
            _sc("high", "治療中及／或血壓 > 140/90", {"status": "high"}, SUB, SUB, SUB, STD, STD),
            _sc("other", "其他", {"status": "other"}, IND, IND, IND, STD, IND),
        ],
    },
    {
        "id": "liver_cysts",
        "name_zh": "肝囊腫",
        "name_en": "Liver Cysts",
        "keywords": ["肝囊腫", "cyst", "肝"],
        "description_zh": "單純性肝囊腫與複雜性／多發性結果不同。",
        "extra_reqs": ["可能需要：超聲波／影像報告"],
        "questions": [
            _q("status", "類型？", [("simple", "單純性、無症狀、無需治療"), ("complex", "複雜／多發或需跟進"), ("treated", "曾介入治療")]),
        ],
        "scenarios": [
            _sc("simple", "單純性、無症狀", {"status": "simple"}, STD, STD, STD, STD, STD),
            _sc("complex", "複雜／多發需跟進", {"status": "complex"}, SUB, SUB, EXC, STD, SUB),
            _sc("treated", "曾介入治療", {"status": "treated"}, IND, IND, EXC, STD, IND),
        ],
    },
    {
        "id": "osa",
        "name_zh": "阻塞性睡眠窒息症（OSA）",
        "name_en": "Obstructive Sleep Apnoea (OSA)",
        "keywords": ["睡眠窒息", "osa", "呼吸機", "cpap", "鼻鼾"],
        "description_zh": "視乎嚴重程度、CPAP 使用及有否其他風險（肥胖、血壓等）。",
        "extra_reqs": ["可能需要：睡眠測試報告"],
        "questions": [
            _q("status", "狀況？", [("mild", "輕度、已改善"), ("cpap", "使用 CPAP／治療中且依從性良好"), ("severe", "中重度未妥善控制")]),
        ],
        "scenarios": [
            _sc("mild", "輕度已改善", {"status": "mild"}, STD_MAY_SUB, STD_MAY_SUB, STD_MAY_SUB, STD, STD),
            _sc("cpap", "CPAP 治療中、依從性良好", {"status": "cpap"}, SUB, SUB, SUB, STD, STD),
            _sc("severe", "未妥善控制", {"status": "severe"}, IND, IND, IND, STD, IND),
        ],
    },
    {
        "id": "prematurity",
        "name_zh": "早產嬰兒",
        "name_en": "Prematurity",
        "keywords": ["早產", "premature", "嬰兒"],
        "description_zh": "適用於早產史。現時發育、併發症與年齡影響評估。",
        "extra_reqs": ["請準備出生孕週、體重及現況"],
        "questions": [
            _q("status", "現況？", [("grown", "已健康成長、無後遺症"), ("follow", "仍需專科跟進"), ("comp", "有明顯後遺症／併發症")]),
        ],
        "scenarios": [
            _sc("grown", "已健康成長、無後遺症", {"status": "grown"}, STD, STD, STD, STD, STD),
            _sc("follow", "仍需專科跟進", {"status": "follow"}, SUB, SUB, SUB, STD, STD),
            _sc("comp", "有明顯後遺症", {"status": "comp"}, IND, IND, IND, STD, IND),
        ],
    },
    {
        "id": "pcos",
        "name_zh": "多囊性卵巢綜合症（PCOS）",
        "name_en": "Polycystic Ovarian Syndrome (PCOS)",
        "keywords": ["pcos", "多囊", "卵巢"],
        "description_zh": "PCOS 常與代謝風險相關。有否糖尿病／肥胖會影響結果。",
        "extra_reqs": ["可能需要：荷爾蒙／血糖相關報告"],
        "questions": [
            _q("status", "狀況？", [("simple", "已確診但代謝指標正常"), ("metabolic", "合併肥胖／血糖異常等"), ("complex", "合併較嚴重內分泌／代謝問題")]),
        ],
        "scenarios": [
            _sc("simple", "代謝指標大致正常", {"status": "simple"}, STD, STD, EXC, STD, STD),
            _sc("meta", "合併代謝風險", {"status": "metabolic"}, SUB, SUB, EXC, STD, STD),
            _sc("complex", "較複雜情況", {"status": "complex"}, IND, IND, EXC_POST, STD, IND),
        ],
    },
    {
        "id": "renal_stones",
        "name_zh": "腎結石",
        "name_en": "Renal Stones / Calculus (Kidney Stones)",
        "keywords": ["腎結石", "结石", "kidney stone", "renal"],
        "description_zh": "單次與復發、有否腎功能受損或手術史會影響醫療核保。",
        "extra_reqs": ["可能需要：影像及腎功能報告"],
        "questions": [
            _q("status", "狀況？", [("single_clear", "單次、已排出／處理、無復發"), ("recurrent", "復發性"), ("comp", "有腎功能影響／複雜手術")]),
        ],
        "scenarios": [
            _sc("single", "單次已處理、無復發", {"status": "single_clear"}, STD, STD, EXC, STD, STD),
            _sc("recur", "復發性腎結石", {"status": "recurrent"}, SUB, SUB, EXC, STD, STD),
            _sc("comp", "影響腎功能或複雜情況", {"status": "comp"}, IND, IND, EXC_POST, STD, IND),
        ],
    },
    {
        "id": "thalassaemia",
        "name_zh": "地中海貧血",
        "name_en": "Thalassaemia",
        "keywords": ["地中海貧血", "thalassaemia", "thalassemia", "帶因"],
        "description_zh": "帶因者與病患者核保差異大。需確認類型及有否貧血症狀／輸血。",
        "extra_reqs": ["可能需要：血色素電泳／CBC"],
        "questions": [
            _q("status", "類型？", [("trait", "帶因者（Trait），無明顯症狀"), ("intermedia", "中間型"), ("major", "重型或需定期輸血")]),
        ],
        "scenarios": [
            _sc("trait", "帶因者、無明顯症狀", {"status": "trait"}, STD, STD, STD, STD, STD),
            _sc("inter", "中間型", {"status": "intermedia"}, SUB, SUB, EXC, STD, SUB),
            _sc("major", "重型／需定期輸血", {"status": "major"}, IND, DEC, DEC, STD, IND),
        ],
    },
    {
        "id": "thyrotoxicosis",
        "name_zh": "甲狀腺功能亢進",
        "name_en": "Thyrotoxicosis (Hyperthyroidism)",
        "keywords": ["甲亢", "甲狀腺", "hyperthyroid", "thyrotoxicosis"],
        "description_zh": "需了解是否已穩定、藥物／放射碘／手術及近期指數。",
        "extra_reqs": ["可能需要：甲狀腺功能報告"],
        "questions": [
            _q("status", "狀況？", [("stable", "已穩定、指數正常、治療完成或維持良好"), ("treating", "治療中尚未穩定"), ("unstable", "反覆或不穩")]),
        ],
        "scenarios": [
            _sc("stable", "已穩定、指數正常", {"status": "stable"}, STD, STD, EXC, STD, STD),
            _sc("treating", "治療中尚未穩定", {"status": "treating"}, SUB, SUB, EXC_POST, STD, STD),
            _sc("unstable", "反覆或不穩", {"status": "unstable"}, IND, IND, POST, STD, IND),
        ],
    },
    {
        "id": "thyroid_nodule",
        "name_zh": "甲狀腺結節",
        "name_en": "Thyroid Nodule",
        "keywords": ["甲狀腺結節", "結節", "thyroid nodule"],
        "description_zh": "良性確認、細針穿刺結果及跟進安排影響評估。",
        "extra_reqs": ["可能需要：超聲波／FNA 報告"],
        "questions": [
            _q("status", "狀況？", [("benign", "已確認良性、穩定"), ("monitor", "需定期監察"), ("suspicious", "可疑或未完成檢查")]),
        ],
        "scenarios": [
            _sc("benign", "已確認良性、穩定", {"status": "benign"}, STD, STD, EXC, STD, STD),
            _sc("monitor", "需定期監察", {"status": "monitor"}, STD_MAY_SUB, SUB, EXC, STD, SUB),
            _sc("susp", "可疑／未完成檢查", {"status": "suspicious"}, POST, POST, POST, STD, POST),
        ],
    },
    {
        "id": "uterine_fibroid",
        "name_zh": "子宮肌瘤",
        "name_en": "Uterine Fibroid",
        "keywords": ["肌瘤", "子宮", "fibroid", "fibroids"],
        "description_zh": "視乎大小、症狀、手術史及跟進。",
        "extra_reqs": ["可能需要：超聲波或手術病理報告"],
        "questions": [
            _q("status", "狀況？", [("small", "細小、無症狀、只需觀察"), ("symptomatic", "有症狀或較大"), ("surgery", "已手術切除並康復")]),
        ],
        "scenarios": [
            _sc("small", "細小無症狀", {"status": "small"}, STD, STD, EXC, STD, STD),
            _sc("sym", "有症狀或較大", {"status": "symptomatic"}, STD, SUB, EXC_POST, STD, STD),
            _sc("surgery", "已手術並康復", {"status": "surgery"}, STD, STD, EXC, STD, STD),
        ],
    },
]
