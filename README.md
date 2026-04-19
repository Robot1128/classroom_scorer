# 课堂内容评分器 v2

FastAPI 服务，部署到 Vercel，供 Coze Bot 通过 HTTP 调用。

## 与 v1 的核心改进

1. **LLM 语义评分**：调用 DeepSeek 等大模型从 4 个维度（准确性/完整性/清晰度/深度）做结构化评分，不再依赖粗糙的关键词匹配
2. **自动降级**：LLM 调用失败或超时时，自动回退到规则评分，保证服务可用
3. **Bearer Token 认证**：防止 URL 泄露后被滥用
4. **标准答案可选**：不再强制依赖标准答案，LLM 根据题目和知识点自行判断

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 核心服务代码 |
| `requirements.txt` | Python 依赖 |
| `vercel.json` | Vercel 部署配置 |
| `.env.example` | 环境变量模板 |

## 部署步骤

1. 注册 Vercel：https://vercel.com（建议用 GitHub 账号）
2. 在 GitHub 新建仓库，上传这 4 个文件
3. Vercel Dashboard → Add New Project → 导入该仓库
4. Framework Preset 选 **Other**
5. Project Settings → Environment Variables，添加：
   - `LLM_API_KEY`：你的 DeepSeek / 其他兼容 OpenAI 接口的 API Key
   - `LLM_API_BASE`（可选）：默认 `https://api.deepseek.com/v1`
   - `LLM_MODEL`（可选）：默认 `deepseek-chat`
   - `API_TOKEN`（可选）：默认 `classroom-scorer-2024`，建议改成你自己的随机字符串
6. 点击 Deploy，约 1-2 分钟完成
7. 获取 URL：`https://xxx.vercel.app`

## 测试

```bash
curl -X POST https://你的地址.vercel.app/score \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer classroom-scorer-2024" \
  -d '{
    "topic": "快速排序",
    "knowledge_point": "分区操作",
    "student_answer": "选择一个基准值，把比它小的放左边，大的放右边，然后递归处理左右两部分",
    "question": "请简述快速排序的核心思想",
    "standard_answer": "选择基准，分区，递归排序"
  }'
```

## 接入 Coze

1. Coze → 「插件」→ 「创建插件」
2. 插件名称：`课堂评分器`
3. 描述：`对学生的课堂回答进行结构化评分，发现知识漏洞`
4. 服务器地址：`https://你的vercel地址.vercel.app`
5. 添加工具：
   - 名称：`score_answer`
   - 路径：`/score`
   - 方法：`POST`
   - Header：`Authorization: Bearer 你的API_TOKEN`
   - 参数：
     | 参数名 | 类型 | 必填 | 说明 |
     |--------|------|------|------|
     | `topic` | string | 是 | 课程主题 |
     | `knowledge_point` | string | 是 | 当前知识点 |
     | `student_answer` | string | 是 | 学生回答 |
     | `question` | string | 否 | 原题目 |
     | `standard_answer` | string | 否 | 标准答案 |
6. 测试工具 → 发布插件
7. 在 Bot 的「技能」→「插件」中添加该插件

## 工作流中的使用建议

### classroom_feedback（反馈工作流）

建议架构：`开始 → 插件(score) → 大模型(包装反馈) → 结束`

大模型节点的输入除 `query/topic/kp` 外，增加插件返回的：
- `score`、`level`、`feedback`、`knowledge_gap`、`suggestion`

大模型提示词示例：
```
你是温和的课堂反馈助手。学生正在学习{{topic}}的第{{kp}}个知识点。

【插件评分结果】
得分：{{score}}/10（{{level}}）
评价：{{feedback}}
知识漏洞：{{knowledge_gap}}
建议：{{suggestion}}

学生回答：{{query}}

请根据以上评分结果，用温暖、鼓励的语气给学生反馈：
1. 简要肯定或指出问题
2. 温和解释知识漏洞
3. 给出具体改进建议
4. 最后问："理解了吗？有疑问随时提出来，我们继续。"

控制在250字以内。
```

### classroom_quiz_summary（grade 模式）

同样调用插件评分，让测验批改更专业。批改后衔接下一题的逻辑保持不变。
