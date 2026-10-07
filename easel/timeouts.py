"""统一超时常量（秒）——CLI / Web / skill 三入口单一真相源。

此前三处各写各的（skill.py=900、web 非流式 chat=300、cli chat=7200），
同一个任务经不同入口会被不同超时掐断、行为不一致。收敛到这里，一处改全生效。

- 制作层 SKILL（生视频 / 多镜合成）由 OpenClaw 自己执行，可能跑很久 → 给足预算。
- 直接执行层（发现 / 策划 / 发布 / 归因）较快。
- chat 入口可能中途触发制作层任务 → 按制作层预算，别被 turn 超时掐断。
"""

TIMEOUT_PRODUCE = 7200   # 制作层：生视频 / 多镜合成给足时间
TIMEOUT_DIRECT = 300     # 轻量直接执行层
TIMEOUT_CHAT = TIMEOUT_PRODUCE   # chat 可能中途触发制作任务，按制作层预算
TIMEOUT_PUBLISH = 600     # Web 发布页同步发布（媒体上传 + 平台处理）
TIMEOUT_XHS_PUBLISH = 1500   # 小红书按真人节奏输入（正文上千字要几分钟）+ 视频处理最长 10 分钟
# 国内浏览器平台「半自动」发布：脚本填好表单后等人亲自点「发布」，最长等 PUBLISH_HANDOFF_TIMEOUT 秒
# （= 各发布脚本 --handoff-timeout 默认值），再加上填表/上传耗时与余量，才是整条子进程的总预算。
PUBLISH_HANDOFF_TIMEOUT = 3600
TIMEOUT_PUBLISH_SEMI_AUTO = PUBLISH_HANDOFF_TIMEOUT + TIMEOUT_XHS_PUBLISH + 300
