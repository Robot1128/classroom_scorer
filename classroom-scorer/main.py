import os
import json
import httpx
import logging
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="课堂内容评分器")
security = HTTPBearer()

logger = logging.getLogger(__name__)

# ---------- 配置 ----------
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.deepseek.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
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

# ---------- 主接口 ----------
@app.post("/score", response_model=ScoreResponse)
async def score_answer(req: ScoreRequest, token: str = Depends(verify_token)):
    """
    学生回答评分接口。
    优先使用 LLM 做语义评分；LLM 不可用或超时时自动降级到规则评分。
    """
    if LLM_API_KEY:
        try:
            return await llm_score(req)
        except Exception as e:
            logger.warning(f"LLM scoring failed: {e}, fallback to rule-based")
    return rule_based_score(req)

# ---------- LLM 评分（主路径） ----------
async def llm_score(req: ScoreRequest) -> ScoreResponse:
    standard_line = f"标准答案：{req.standard_answer}" if req.standard_answer else ""

    prompt = f"""你是资深教学评估专家。请严格按以下要求对学生回答评分。

【评估信息】
课程主题：{req.topic}
知识点：{req.knowledge_point}
{"题目：" + req.question if req.question else ""}
{standard_line}

【学生回答】
{req.student_answer}

【评分规则】（总分 10 分）
1. 准确性（0-4 分）：概念是否正确、有无原理性错误
2. 完整性（0-3 分）：是否覆盖该知识点的核心要点
3. 表达清晰度（0-2 分）：逻辑是否连贯、语言是否准确
4. 深度与迁移（0-1 分）：是否有自己的理解、举例或延伸

【输出格式】
必须且仅输出以下 JSON，不要 markdown 代码块、不要解释：
{{"score": 整数, "level": "优秀"/"良好"/"一般"/"需加强", "feedback": "2-3句具体评价", "knowledge_gap": "1句知识漏洞描述，无则写'无明显漏洞'", "suggestion": "1句改进建议"}}"""

    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.post(
            f"{LLM_API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "你只输出纯 JSON，不要任何解释、markdown 代码块标记或其他文字。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 400
            }
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # 清理可能的 markdown 代码块
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        result = json.loads(content)

        # 校验与兜底
        score = max(1, min(10, int(result.get("score", 5))))
        level = result.get("level", _score_to_level(score))
        if level not in ("优秀", "良好", "一般", "需加强"):
            level = _score_to_level(score)

        return ScoreResponse(
            score=score,
            level=level,
            feedback=result.get("feedback", "已收到回答"),
            knowledge_gap=result.get("knowledge_gap", "无明显漏洞"),
            suggestion=result.get("suggestion", "继续保持")
        )

# ---------- 规则评分（降级兜底） ----------
def rule_based_score(req: ScoreRequest) -> ScoreResponse:
    answer = req.student_answer.strip().lower()
    score = 5
    feedback_parts = []
    gap = ""
    suggestion = ""

    # 1. 长度
    if len(answer) < 5:
        score -= 2
        feedback_parts.append("回答过于简短，建议展开说明")
        gap = "表达不够完整"
        suggestion = "尝试用自己的话详细描述概念"
    elif len(answer) > 80:
        score += 1
        feedback_parts.append("回答较为详细")

    # 2. 专业关键词（学科通用）
    keywords = ["概念", "原理", "步骤", "方法", "因为", "所以", "例如", "首先", "然后"]
    matched = sum(1 for kw in keywords if kw in answer)
    if matched >= 4:
        score += 2
        feedback_parts.append("涉及多个核心概念")
    elif matched >= 2:
        score += 1
        feedback_parts.append("部分概念理解正确")
    else:
        score -= 1
        gap = "缺少关键概念或结构化表达"
        suggestion = "尝试使用更专业的术语并分步骤说明"

    # 3. 标准答案方向
    if req.standard_answer and req.standard_answer.strip().lower() in answer:
        score += 1
        feedback_parts.append("与标准答案方向一致")

    score = max(1, min(10, score))

    return ScoreResponse(
        score=score,
        level=_score_to_level(score),
        feedback="；".join(feedback_parts) if feedback_parts else "已收到回答",
        knowledge_gap=gap or "无明显漏洞",
        suggestion=suggestion or "继续保持"
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
    return {
        "message": "课堂内容评分器 API 运行中",
        "version": "2.0",
        "llm_ready": bool(LLM_API_KEY)
    }

@app.get("/health")
async def health():
    return {"status": "ok", "llm_ready": bool(LLM_API_KEY)}
