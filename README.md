# 知情拒绝下的见习机会核算与补学改约

教务轮转台账、现场回执和可预约补学时段的合成交换样本。 数据不含真实学生、患者或就诊记录。数据表在 `data/`，业务字段和交换约定见 [资料口径](data-contract.md)。

在 Python 3.11 下可直接清点资料和检查表结构。统计环境使用 `requirements.txt` 中锁定的版本，可在虚拟环境中一次安装后离线使用。

```sh
python3 -m pip install -r requirements.txt
python3 inspect_bundle.py data
python3 -m unittest discover -s tests -v
```

资料检查入口只读，输出每张表的记录数，读取到不符合清单的表时退出。空白字段按资料口径解释。
