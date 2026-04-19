import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="课堂内容评分器")
security = HTTPBearer()

# ---------- 配置 ----------
API_TOKEN = os.environ.get("API_TOKEN", "classroom-scorer-2024")

# ---------- 模型 ----------
class ScoreRequest(BaseModel):
    topic: str
    knowledge_point: str
    student_answer: str
    standard_answer: Optional[str] = ""
    question: Optional[str] = ""

class ScoreResponse(BaseModel):
    score: int          # 1-10
    level: str          # 优秀/良好/一般/需加强
    feedback: str
    knowledge_gap: str
    suggestion: str

# ---------- 认证 ----------
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials

# ---------- 按主题+知识点的关键词库 ----------
KEYWORDS_DB = {
    ("快速排序", "分区操作"): ["基准", "pivot", "分区", "小于", "大于", "递归"],
    ("快速排序", "核心概念"): ["分治", "递归", "基准", "平均", "最坏", "O(nlogn)"],
    ("快速排序", "复杂度分析"): ["O(nlogn)", "O(n²)", "平均", "最坏", "空间", "原地"],
    ("二分查找", "核心思想"): ["有序", "中间", "折半", "O(logn)", "减半"],
    ("二分查找", "边界条件"): ["左边界", "右边界", "闭区间", "开区间", "死循环"],
    ("栈", "基本概念"): ["后进先出", "LIFO", "压栈", "弹栈", "栈顶"],
    ("队列", "基本概念"): ["先进先出", "FIFO", "入队", "出队", "队首", "队尾"],
}

# 通用结构词（表达是否清晰）
STRUCTURE_WORDS = ["因为", "所以", "例如", "首先", "然后", "步骤", "过程", "总结"]

# ---------- 主接口 ----------
@app.post("/score", response_model=ScoreResponse)
async def score_answer(req: ScoreRequest, token: str = Depends(verify_token)):
    return rule_based_score(req)

# ---------- 规则评分（核心） ----------
def rule_based_score(req: ScoreRequest) -> ScoreResponse:
    answer = req.student_answer.strip()
    answer_lower = answer.lower()
    topic = req.topic.strip()
    kp = req.knowledge_point.strip()
    standard = req.standard_answer.strip()

    score = 5
    feedback_parts = []
    gap = ""
    suggestion = ""

    # 1. 长度评估
    if len(answer) < 3:
        score -= 3
        feedback_parts.append("回答过于简短")
        gap = "几乎没有实质内容"
        suggestion = "请用自己的话详细解释概念"
    elif len(answer) < 10:
        score -= 2
        feedback_parts.append("回答偏短，缺少展开")
        gap = "表达不够完整"
        suggestion = "尝试分步骤或举例说明"
    elif len(answer) > 50:
        score += 1
        feedback_parts.append("回答比较详细")

    # 2. 关键词匹配（优先用主题库，没有则用通用词）
    key = (topic, kp)
    keywords = KEYWORDS_DB.get(key, [])

    if keywords:
        matched = sum(1 for kw in keywords if kw.lower() in answer_lower)
        ratio = matched / len(keywords)

        if ratio >= 0.6:
            score += 3
            feedback_parts.append("核心概念掌握准确")
        elif ratio >= 0.3:
            score += 1
            feedback_parts.append("部分概念理解正确")
            gap = gap or "部分核心概念缺失"
            suggestion = suggestion or f"重点回顾：{', '.join(keywords[:3])}"
        else:
            score -= 2
            feedback_parts.append("缺少关键概念")
            gap = gap or "核心概念理解有误"
            suggestion = suggestion or f"建议重新学习：{', '.join(keywords[:3])}"
    else:
        # 通用评分：结构词
        struct_matched = sum(1 for w in STRUCTURE_WORDS if w in answer_lower)
        if struct_matched >= 3:
            score += 2
            feedback_parts.append("表达结构清晰")
        elif struct_matched >= 1:
            score += 1
        else:
            score -= 1
            feedback_parts.append("缺少结构化表达")

    # 3. 标准答案比对（有标准答案时才启用）
    if standard:
        std_lower = standard.lower()
        # 标准答案分词匹配
        std_words = [w.strip() for w in std_lower.replace("。", " ").replace("，", " ").split() if len(w.strip()) > 1]
        if std_words:
            hit = sum(1 for w in std_words if w in answer_lower)
            match_rate = hit / len(std_words)
            if match_rate >= 0.5:
                score += 2
                feedback_parts.append("与标准答案方向一致")
            elif match_rate >= 0.2:
                score += 1
            else:
                score -= 1
                feedback_parts.append("与标准答案偏差较大")
                gap = gap or "理解方向可能有偏差"

    # 4. 特殊加分/减分
    if "不懂" in answer or "不会" in answer or "不知道" in answer:
        score = max(1, score - 2)
        feedback_parts.append("疑似未理解题目")
        gap = gap or "尚未掌握该知识点"
        suggestion = suggestion or "建议重新学习相关内容"

    score = max(1, min(10, score))

    return ScoreResponse(
        score=score,
        level=_score_to_level(score),
        feedback="；".join(feedback_parts) if feedback_parts else "已收到回答",
        knowledge_gap=gap or "无明显漏洞",
        suggestion=suggestion or "继续保持，深入理解"
    )

# ---------- 工具函数 ----------
def _score_to_level(score: int) -> str:
    if score >= 9:
        return "优秀"
    if score >= 7:
        return "良好"
    if score >= 5:
        return "一般"
    return "需加强"

# ---------- 健康检查 ----------
@app.get("/")
async def root():
    return {"message": "课堂内容评分器 API 运行中", "version": "2.1-rule", "mode": "rule-based"}

@app.get("/health")
async def health():
    return {"status": "ok", "mode": "rule-based"}
