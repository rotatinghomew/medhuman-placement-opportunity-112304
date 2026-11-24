# 知情拒绝下的见习机会核算与补学改约

教务轮转台账、现场回执和可预约补学时段的合成交换样本。数据不含真实学生、患者或就诊记录。数据表在 `data/`，业务字段和交换约定见 [资料口径](data-contract.md)。

## 资料检查

在 Python 3.11 下可直接清点资料和检查表结构：

```sh
python3 -m pip install -r requirements.txt
python3 -I inspect_bundle.py data
python3 -m unittest discover -s tests -v
```

资料检查入口只读，输出每张表的记录数，读取到不符合清单的表时退出。空白字段按资料口径解释。

## 每轮重跑核算与补学

核算核心只依赖标准库；按 `requirements.txt` 安装 SciPy 后，补学匹配会使用全局整数规划比较整轮安排。

```sh
python3 -I solve.py data --out out
```

常用参数：

```sh
# 按某个证据收件时点重算草案（例如夜间回执到达前 4830、到达后 6950）
python3 -I solve.py data --out out --as-of 6950 --now 6950

# 比较旧草案和新证据，并输出 S5 被迟到 present 回执撤销损失等变化
python3 -I solve.py data --out out --compare-old 4830 --compare-new 6950

# 查询某个原轮转的指标、补学决定和依据
python3 -I solve.py data --query-rotation R1

# 协调员已取得学生一次换约同意后重跑
cat > /tmp/consents.json <<'JSON'
[{"student":"S4","from":"O6","to":"O10"}]
JSON
python3 -I solve.py data --consents /tmp/consents.json --out out-consent
```

## 输出口径

`out/` 中包含：

- `report.md`：给协调员看的中文复核报告。
- `result.json`：全部结构化结果。
- `opportunity_accounting.csv`：学生-机会明细，保留通知、可达性、最新回执、带教、许可和归因。
- `rotation_metrics.csv` / `rotation_decisions.csv`：按学生**原轮转**汇总的三种口径、损失来源、补学决定和依据。
- `opportunity_metrics.csv`：每个教学机会的带教、许可、保护容量和剩余容量。
- `student_gaps.csv`：按课程义务算出的必修缺口、模拟是否被承认、补偿/申请路径。
- `remediation_assignments.csv`：基线整轮安排。
- `unresolved_gaps.csv`：截止前无法补足的具体限制。
- `swap_consultations.csv`：可征询的一次性换约、条件式整轮效果和得失。
- `do_not_send.csv`：已完成/已保护/容量满/许可未清等不应重复发出的安排。
- `event_claims.csv`：同一 `activity` 只形成一次完成主张，防止同一临床事件重复上报。
- `draft_changes.csv` / `.json`：指定两个证据时点之间的草案变化。

核算原则：

1. **三种口径**：`planned_bookings` 是通知预约数；`planned_attendable` 还要求按已有课表、路程和受保护预约能按时到达；`actual_attendable` 再计入取消、同意撤回、许可人数、带教资格和现场容量；`completed` 只认有效 `present` 回执。
2. **不把缺回执记成缺席**：没有最终 `no_show` 时，已过时段只标为 `final_receipt_missing` 或 `held_appointment_without_final_receipt`，来源为“资料无法确定”。
3. **损失来源分开**：`supervision`（带教不足）、`activity`（活动取消、家属/同意撤回、许可为零或容量被到场者占满）、`student`（时间/路程冲突或已确认缺席）、`undetermined`。
4. **补偿资格分开**：院方/带教口径成立的损失进入 `priority_compensation`；确认缺席进入 `student_application`，只在保障后余量中按申请顺序处理。
5. **整轮匹配**：截止日最早优先；同一保障层内只有一个合格时段/方式的缺口优先于有两个时段的缺口；再按 `apply_order`。评分只用于同条件平局，不允许单人最高分选择破坏唯一选项者。
6. **保护与换约**：已接受课业和预约均为硬冲突/已占容量。工具不会自动释放旧预约，只生成“可征询换约”和条件式预览；每名学生最多确认一次换约。
7. **模拟边界**：模拟位有独立并行容量；只有 `obligation.simulation_allowed=1` 的课程/场景可用模拟补缺口，不合规模拟完成不会被计为该必修场景。
