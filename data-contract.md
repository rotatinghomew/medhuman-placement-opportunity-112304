# 资料口径

院系以生号和轮转号识别见习。课表以三元组（日、开始分钟、结束分钟）标记当地时间，区间左闭右开；机会可在同一病房的同一教学活动下有多个候选观察位。旅行用分钟，最短到场时间来自学生已有课表的地点。临床事件号是同一教学活动的识别键，模拟活动另用编号。
回执里的 `cancelled`、`refused`、`present`、`no_show`、`held` 分别表示机会未发生、同意撤回、学生到场、已确认未到、预约已接受；回执时间是教务收件分钟，可跨日按“日×1440＋分钟”比较。授权中的 `allowed` 是该次许可允许继续的观察人数，零为明确拒绝。补学先保证截止较早的必修缺口，其次保证仅有一种合格补学方式的人，再按已公布的学生申请时间排序。已确认缺席按自行申请规则处理，不进入这次优先补偿。

数据表使用 UTF-8 CSV，第一行是字段名。同一业务号的引用指数据字典约定的原始对象；空白表示来源未提供，集合字段由逗号分隔后整体按 CSV 转义。
- `student.csv` 的字段为 `id`、`course`、`rotation`、`home`、`apply_order`、`deadline`。
- `obligation.csv` 的字段为 `course`、`scenario`、`required`、`simulation_allowed`。
- `travel.csv` 的字段为 `origin`、`destination`、`minutes`。
- `busy.csv` 的字段为 `student`、`day`、`begin`、`end`、`location`。
- `supervisor.csv` 的字段为 `teacher`、`scenario`、`mode`、`start_day`、`end_day`。
- `opportunity.csv` 的字段为 `id`、`activity`、`rotation`、`day`、`begin`、`end`、`place`、`scenario`、`mode`、`teachers`、`capacity`。
- `announcement.csv` 的字段为 `student`、`opportunity`、`sent_at`、`status`。
- `permission.csv` 的字段为 `activity`、`restricted_mode`、`allowed`、`valid_from`、`received_at`。
- `receipt.csv` 的字段为 `id`、`student`、`opportunity`、`status`、`received_at`、`supersedes`。
