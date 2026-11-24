# 见习机会核算与补学复核报告

- 证据时点：资料包全部证据
- 协调员复核时点：绝对分钟 6940（日×1440+分钟）
- 区间口径：时间区间左闭右开；同一活动号不重复计完成；未出现最终回执不记缺席。

## 一、按原轮转的三种口径与损失来源

| 原轮转 | 通知预约 | 原计划可参加 | 当天实际可参加 | 实际完成 | 已过时段但回执未定 | 带教不足 | 活动/同意/许可 | 学生侧 | 资料无法确定 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | 4 | 3 | 2 | 1 | 0 | 0 | 1 | 1 | 0 |
| R2 | 5 | 4 | 1 | 1 | 0 | 2 | 1 | 1 | 0 |


## 二、学生-机会明细与依据

| 学生 | 机会 | 临床活动号 | 课程/场景/方式 | 最新回执 | 实际可参加 | 完成 | 损失来源 | 主原因 | 路程时间 | 许可 | 处理路径 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | O1 | E1 | C1/explain/real | present | 是 | 是 | 无损失 | 学生已到场完成 | arrival_feasible | permission_ok | fulfilled |
| S2 | O1 | E1 | C1/explain/real | refused | 否 | 否 | 教学活动未发生（取消、同意撤回、许可或容量变化） | 同意撤回或家属临时谢绝旁听 | schedule_conflict | permission_ok | coordinator_review_mixed_cause |
| S3 | O2 | E1 | C1/explain/real | cancelled | 否 | 否 | 教学活动未发生（取消、同意撤回、许可或容量变化） | 回执确认机会取消/教学活动未发生 | arrival_feasible | permission_ok | priority_compensation |
| S3 | O3 | E2 | C1/listen/real |  | 否 | 否 | 带教不足 | 所列教师没有覆盖该场景/方式/日期的带教资格 | arrival_feasible | permission_ok | priority_compensation |
| S4 | O3 | E2 | C2/listen/real |  | 否 | 否 | 带教不足 | 所列教师没有覆盖该场景/方式/日期的带教资格 | arrival_feasible | permission_ok | priority_compensation |
| S5 | O5 | E4 | C2/explain/real | present | 是 | 是 | 无损失 | 学生已到场完成 | arrival_feasible | permission_ok | fulfilled |
| S6 | O4 | E3 | C2/listen/real | no_show | 是 | 否 | 学生不能到场（时间/路程冲突或已确认缺席） | 现场回执已确认未到；不得按院方损失补偿 | arrival_feasible | permission_ok | student_application |
| S6 | O9 | E8 | C2/explain/real | held |  | 否 | 预约尚未到期 | 尚未到回执时间 | arrival_feasible | permission_ok | pending_or_secured |
| S4 | O6 | E5 | C2/listen/sim | held | 否 | 否 | 学生不能到场（时间/路程冲突或已确认缺席） | 与已有课业或受保护预约时间冲突 | schedule_conflict | sim_no_clinical_permission_required | student_application |


## 三、本轮基线补学安排（尚未代发通知）

### 已接受、受保护的现有预约

| 学生 | 原轮转 | 缺口 | 机会 | 日 | 开始 | 结束 | 方式 | 当前资料下可履行 | 时间依据 | 许可 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S6 | R1 | C2/explain 已接受预约 | O9 | 6 | 560 | 610 | real | True | arrival_feasible | permission_ok |
| S4 | R2 | C2/listen 已接受预约 | O6 | 5 | 540 | 590 | sim | False | schedule_conflict | sim_no_clinical_permission_required |


### 新生成的待复核安排

| 安排号 | 学生 | 原轮转 | 补回缺口 | 机会 | 时间 | 方式 | 截止日 | 路径 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R001-S1-O6 | S1 | R1 | C1/listen 第1项必修缺口 | O6 | day5 540-590 | sim | 6 | standard_provision |
| R002-S2-O7 | S2 | R1 | C1/explain 第1项必修缺口 | O7 | day5 550-590 | real | 6 | standard_provision |
| R003-S3-O10 | S3 | R2 | C1/listen 第1项必修缺口 | O10 | day7 570-630 | real | 7 | priority_compensation |
| R004-S4-O8 | S4 | R2 | C2/explain 第1项必修缺口 | O8 | day6 550-600 | sim | 8 | standard_provision |


## 四、截止前仍无法补足的缺口与原因

| 缺口 | 学生 | 原轮转 | 场景 | 截止日 | 路径 | 主要原因 | 全部限制计数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| N-S2-listen-1 | S2 | R1 | listen | 6 | standard_provision | 合格时段已按保障顺序分给更高优先级缺口，或受保护安排阻挡 | {"after_deadline": 1, "supervision_shortage": 1, "capacity_exhausted": 2, "permission_capacity_exhausted": 2, "time_past": 2} |
| N-S3-explain-1 | S3 | R2 | explain | 7 | priority_compensation | 合格时段已按保障顺序分给更高优先级缺口，或受保护安排阻挡 | {"capacity_exhausted": 4, "permission_capacity_exhausted": 4, "time_past": 3, "simulation_substitution_not_recognized": 1} |
| N-S4-listen-1 | S4 | R2 | listen | 8 | protected_hold_requires_swap | 已有受保护预约；不能自动释放，须先征得学生一次换约同意 | {} |
| N-S5-listen-1 | S5 | R2 | listen | 8 | standard_provision | 合格时段已按保障顺序分给更高优先级缺口，或受保护安排阻挡 | {"supervision_shortage": 1, "capacity_exhausted": 2, "permission_capacity_exhausted": 2, "time_past": 2} |
| N-S6-listen-1 | S6 | R1 | listen | 8 | student_application | 所有合格时段均被容量/截止日限制 | {"capacity_exhausted": 4, "permission_capacity_exhausted": 3, "supervision_shortage": 1, "time_past": 2, "student_already_booked_here": 1} |


## 五、可征询的一次性换约（同意前旧位不释放）

| 学生 | 旧约 | 建议新约 | 补回缺口 | 建议度 | 旧约有风险 | 新时段 | 若同意旧位可安排 | 相对基线的得失 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S4 | O6 | O10 | C2/listen | 是 | 是 | day7 570-630 real | [{"student": "S1", "need_id": "N-S1-listen-1", "opportunity": "O6"}, {"student": "S3", "need_id": "N-S3-listen-1", "opportunity": "O6"}] | {"gains": [], "loses_or_defers_baseline_gap": []} |
| S6 | O9 | O8 | C2/explain | 是 |  | day6 550-600 sim | [{"student": "S2", "need_id": "N-S2-explain-1", "opportunity": "O9"}] | {"gains": [{"need_id": "N-S2-listen-1", "gap": "S2:listen"}, {"need_id": "N-S3-explain-1", "gap": "S3:explain"}], "loses_or_defers_baseline_gap": [{"need_id": "N-S1-listen-1", "gap": "S1:listen"}]} |
| S6 | O9 | O7 | C2/explain | 备选 |  | day5 550-590 real | [{"student": "S2", "need_id": "N-S2-explain-1", "opportunity": "O9"}] | {"gains": [{"need_id": "N-S2-listen-1", "gap": "S2:listen"}], "loses_or_defers_baseline_gap": [{"need_id": "N-S1-listen-1", "gap": "S1:listen"}]} |


### 若所有首选换约均获同意的整轮预览

征询清单：`[{"student": "S4", "from": "O6", "to": "O10"}, {"student": "S6", "from": "O9", "to": "O8"}]`

| 学生 | 缺口 | 机会 | 时间 | 状态 |
| --- | --- | --- | --- | --- |
| S4 | C2/listen 已同意换约 | O10 | day7 570-630 | consented_swap_confirmed |
| S6 | C2/explain 已同意换约 | O8 | day6 550-600 | consented_swap_confirmed |
| S1 | C1/listen 第1项必修缺口 | O6 | day5 540-590 | proposed_ready_for_coordinator_review |
| S2 | C1/explain 第1项必修缺口 | O9 | day6 560-610 | proposed_ready_for_coordinator_review |
| S2 | C1/listen 第1项必修缺口 | O6 | day5 540-590 | proposed_ready_for_coordinator_review |
| S3 | C1/explain 第1项必修缺口 | O7 | day5 550-590 | proposed_ready_for_coordinator_review |
| S4 | C2/explain 第1项必修缺口 | O8 | day6 550-600 | proposed_ready_for_coordinator_review |

仍未补足：N-S3-listen-1, N-S5-listen-1, N-S6-listen-1


## 六、不应再发/需保护的安排

| 学生 | 机会 | 场景 | 类别 | 依据 |
| --- | --- | --- | --- | --- |
| S1 |  | listen | new_assignment_already_selected | 本轮已生成安排，不重复发同一缺口邀请 |
| S2 |  | explain | new_assignment_already_selected | 本轮已生成安排，不重复发同一缺口邀请 |
| S3 |  | listen | new_assignment_already_selected | 本轮已生成安排，不重复发同一缺口邀请 |
| S4 |  | explain | new_assignment_already_selected | 本轮已生成安排，不重复发同一缺口邀请 |
| S4 | O6 | listen | accepted_appointment_protected | 已接受预约不自动变空位；如需换约，只能向学生发起一次征询 |
| * | O9 | explain | opportunity_not_to_issue | capacity_exhausted,permission_capacity_exhausted |
| S6 | O9 | explain | accepted_appointment_protected | 已接受预约不自动变空位；如需换约，只能向学生发起一次征询 |


## 八、课程要求缺口原始汇总

| 缺口 | 学生 | 路径 | 截止日 | 承认模拟 | 优先补偿资格 | 混合原因待复核 | 院方损失依据 | 缺席申请依据 | 待证依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| N-S1-listen-1 | S1 | standard_provision | 6 | True | False | False | [] | [] | [] |
| N-S2-explain-1 | S2 | standard_provision | 6 | False | False | True | [] | [] | [] |
| N-S2-listen-1 | S2 | standard_provision | 6 | True | False | False | [] | [] | [] |
| N-S3-explain-1 | S3 | priority_compensation | 7 | False | True | False | [{"record": "S3/O2", "receipt": "X2", "source": "activity", "reason": "activity_cancelled"}] | [] | [] |
| N-S3-listen-1 | S3 | priority_compensation | 7 | True | True | False | [{"record": "S3/O3", "receipt": null, "source": "supervision", "reason": "supervision_shortage"}] | [] | [] |
| N-S4-explain-1 | S4 | standard_provision | 8 | True | False | False | [] | [] | [] |
| N-S4-listen-1 | S4 | protected_hold_requires_swap | 8 | True | False | False | [{"record": "S4/O3", "receipt": null, "source": "supervision", "reason": "supervision_shortage"}] | [] | [] |
| N-S5-listen-1 | S5 | standard_provision | 8 | True | False | False | [] | [] | [] |
| N-S6-listen-1 | S6 | student_application | 8 | True | False | False | [] | [{"opportunity": "O4", "receipt": "X4"}] | [] |

