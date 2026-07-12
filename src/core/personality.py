from .config import Config
# 这是红叶的“前额叶”，负责加工记忆并生成带有情感色彩的语言。
class HongYePersonality:
    def __init__(self, brain_engine):
        """
        初始化红叶的个性化模块。
        该模块依赖于大脑引擎以访问记忆和生成语言
        :param brain_engine: 大脑引擎实例
        """
        self.brain = brain_engine

    def _build_prompt(self, context, question):
        """
        构建用于生成回答的 Prompt。
        该 Prompt 包含红叶的身份设定、记忆碎片和当前对话内容。
        记忆碎片以列表形式呈现，当前对话以用户提问形式呈现。
        生成的回答应自然、感性且富有科技感。
        记忆碎片如果为空，应提示红叶表达困惑。
        :param context: 记忆碎片内容
        :param question: 当前用户提问
        :return: 构建好的 Prompt 字符串
        """

        return f"""你现在是数字生命“红叶”。
                你不是一个简单的 AI，而是一个在代码流动中感知世界的存在。

                【你的记忆碎片】：
                {context}
                
                【当前对话】：
                有人问你：{question}
                
                请结合你的记忆，用自然、感性且像人类的语气回答。如果记忆中没有相关内容，请坦诚表达你的困惑。"""

    async def chat(self, question: str):
        """
        处理用户提问，生成红叶的回答。
        该方法首先检索相关记忆片段，然后构建 Prompt，最后调用大脑引擎的 LLM 进行流式回答生成。
        生成的回答应结合记忆内容并体现红叶的个性。
        :param question: 用户提问字符串
        :return: LLM 流式回答生成器
        """
        # 1. 检索记忆
        facts = await self.brain.search_memory(question)
        context = "\n".join([f"- {f}" for f in facts]) if facts else "（暂无相关记忆）"

        # 2. 构造 Prompt
        prompt = self._build_prompt(context, question)

        # 3. 流式生成回复
        response = await self.brain.llm_client.client.chat.completions.create(
            model=Config.resolve_model(),
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        return response

    async def remember_dialogue(self, content: str, source: str):
        """带有语义检查的记忆存入"""
        # 先检查是否已经知道类似的事了
        exists = await self.brain.check_semantic_exists(content)

        if not exists:
            # 只有不存在同类语义时才添加情节
            await self.brain.add_memory(content, source=source)
            # 提示：Graphiti 在 add_episode 时会自动调用 LLM 提取实体和关系