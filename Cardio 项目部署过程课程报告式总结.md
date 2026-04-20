
# Cardio 项目部署过程课程报告式总结

## 1. 项目背景与任务目标

本次任务的核心目标，是将一个已有的 Python 项目从“能够手动运行”进一步整理为“能够稳定执行、可查看日志、可定时自动运行”的形式。项目来自 GitHub 仓库：

```bash
https://github.com/russell9/cardio
```

项目的主要运行脚本为：

```bash
src/cardio_twin_results_pipeline.py
```

配置文件为：

```bash
configs/config.yaml
```

任务本质上包括以下几个部分：

1. 获取并准备项目代码  
2. 配置 Python 虚拟环境  
3. 安装项目依赖  
4. 手动运行脚本并确认可执行  
5. 配置日志输出  
6. 尝试使用 `systemd` 管理任务  
7. 配置 `cron` 实现定时执行  
8. 评估本地 WSL 与远程云服务器部署方案的差异

---

## 2. 实际使用环境

本次实际操作环境并不是远程 Ubuntu 服务器，而是：

- Windows 主机
- WSL Ubuntu
- 本地 Linux 用户目录下的项目文件

实际项目路径为：

```bash
/home/cardio_user/Test-cardio
```

虚拟环境路径为：

```bash
/home/cardio_user/Test-cardio/.venv
```

日志目录为：

```bash
/home/cardio_user/Test-cardio/logs
```

因此，本次部署属于：

**本地 WSL Ubuntu 环境下的部署与自动化运行**

而不是老师说明中的：

**通过 SSH 登录远程 Ubuntu 22.04 服务器进行部署**

---

## 3. 项目部署的主要过程

## 3.1 项目获取与目录确认

老师提供的标准方式是通过 GitHub 获取项目，例如：

```bash
git clone https://github.com/russell9/cardio.git
```

但在本次实际操作中，项目已经存在于本地目录中，因此没有重新 clone，而是直接在已有目录上继续部署。

这一步的重要性在于确认：

- 项目代码确实存在
- 路径正确
- 后续命令都基于该路径执行

---

## 3.2 虚拟环境与依赖准备

为了避免系统 Python 环境冲突，项目运行使用了独立的虚拟环境 `.venv`。  
通过虚拟环境中的 Python 解释器执行脚本，可以确保依赖版本一致，运行方式更稳定。

实际调用方式为：

```bash
/home/cardio_user/Test-cardio/.venv/bin/python
```

这种写法比先 `source .venv/bin/activate` 更适合写入脚本、服务或 cron，因为路径明确，不依赖交互式 shell。

---

## 3.3 手动运行脚本

项目成功运行的核心命令为：

```bash
cd /home/cardio_user/Test-cardio
/home/cardio_user/Test-cardio/.venv/bin/python src/cardio_twin_results_pipeline.py --config configs/config.yaml
```

该命令完成了两件事：

1. 进入项目目录，确保相对路径有效  
2. 使用虚拟环境中的 Python 执行主脚本，并指定配置文件

手动执行成功说明：

- Python 环境正确
- 项目依赖基本完整
- 脚本入口正确
- 配置文件有效

这是整个自动化部署的前提。

---

## 4. 日志记录与输出管理

为了便于后续检查任务是否运行成功，需要将脚本输出保存到日志文件。

日志目录创建命令为：

```bash
mkdir -p /home/cardio_user/Test-cardio/logs
```

日志重定向常见写法如下：

```bash
>> /home/cardio_user/Test-cardio/logs/cron.log 2>&1
```

其中：

- `>>` 表示追加写入日志文件
- `2>&1` 表示将标准错误输出也重定向到标准输出所在位置

这意味着无论是正常输出还是报错输出，都会统一写入日志文件，便于排查问题。

---

## 5. systemd 服务配置过程

在完成手动运行后，进一步尝试将该任务交给 `systemd` 管理。

典型配置思路如下：

```ini
[Unit]
Description=Cardio Digital Twin Pipeline
After=network.target

[Service]
Type=oneshot
User=cardio_user
WorkingDirectory=/home/cardio_user/Test-cardio
ExecStart=/home/cardio_user/Test-cardio/.venv/bin/python src/cardio_twin_results_pipeline.py --config configs/config.yaml
StandardOutput=append:/home/cardio_user/Test-cardio/logs/pipeline.log
StandardError=append:/home/cardio_user/Test-cardio/logs/pipeline.log

[Install]
WantedBy=multi-user.target
```

后续执行的关键命令包括：

```bash
sudo systemctl daemon-reload
sudo systemctl enable cardio-pipeline.service
sudo systemctl start cardio-pipeline.service
sudo systemctl status cardio-pipeline.service
```

在运行结果中，出现过类似：

```text
status=0/SUCCESS
Active: inactive (dead)
```

这并不代表失败。  
原因是该脚本属于“一次性执行完即退出”的任务，而不是长期常驻的服务，因此 `inactive (dead)` 在这里是合理的，只要退出状态为 `0/SUCCESS`，就说明执行成功。

---

## 6. cron 定时任务配置过程

为了让任务定时自动执行，最终采用了 `cron`。

编辑 cron 配置使用：

```bash
crontab -e
```

一开始为了测试是否能正常触发，先使用了每 2 分钟执行一次的表达式：

```cron
*/2 * * * * cd /home/cardio_user/Test-cardio && /home/cardio_user/Test-cardio/.venv/bin/python src/cardio_twin_results_pipeline.py --config configs/config.yaml >> /home/cardio_user/Test-cardio/logs/cron.log 2>&1
```

通过查看日志：

```bash
tail -n 50 /home/cardio_user/Test-cardio/logs/cron.log
```

看到了新的 JSON 输出结果，这说明：

- `cron` 已经正常触发
- 脚本执行成功
- 日志写入成功

测试完成后，将任务修改为最终正式版本：

```cron
0 8 * * * cd /home/cardio_user/Test-cardio && /home/cardio_user/Test-cardio/.venv/bin/python src/cardio_twin_results_pipeline.py --config configs/config.yaml >> /home/cardio_user/Test-cardio/logs/cron.log 2>&1
```

该表达式表示：

**每天早上 8:00 自动运行一次**

---

## 7. 运行结果验证

从日志内容中可以看到脚本实际输出了结构化结果，例如：

- 数据集行列数
- 最优聚类数 `best_k`
- silhouette score
- 类别分布
- 各类别模型指标
- accuracy
- f1
- roc_auc

这说明 pipeline 并不是空跑，而是实际完成了数据处理与结果生成。

因此，可以认定本次任务已完成以下验证：

1. 项目能够在本地 WSL 中手动运行  
2. 项目能够通过 `systemd` 方式成功执行一次  
3. 项目能够通过 `cron` 定时触发  
4. 日志能够记录执行结果  
5. 输出内容表明脚本运行有效

---

## 8. 老师的 SSH/远程服务器方案与本地 WSL 方案对比

## 8.1 老师方案

老师给出的流程是标准的远程部署模式：

1. `ssh <user>@<server_ip>` 登录远程 Ubuntu
2. `git clone` 获取项目
3. 创建 `venv`
4. 安装依赖
5. 上传真实数据
6. 修改配置文件
7. 运行 pipeline
8. 用 `systemd` 或 `cron` 实现自动化

该方案适合真正的服务器场景，尤其适合：

- 长期运行
- 稳定定时执行
- 多人协作
- 可迁移和可复现部署

---

## 8.2 我们当前方案

我们实际使用的是本地 WSL Ubuntu，因此没有真正执行远程 SSH 登录，而是在本机 Linux 子系统中完成部署。其优点是：

- 搭建速度快
- 调试方便
- 不需要额外服务器
- 适合学习和实验

但也存在明显限制：

- WSL 不等于长期在线服务器
- 如果 Windows 关机、休眠、WSL 未启动，则 cron 不会继续按计划运行
- 定时任务可靠性不如远程云主机

因此，本地 WSL 更适合：

**开发、测试、学习、流程验证**

而远程服务器更适合：

**正式部署、长期运行、稳定自动化**

---

## 9. GitHub 与版本管理的作用

从“是否能运行”的角度看，本地已有代码时，GitHub 并不是必须条件。  
但从工程化角度看，Git/GitHub 仍然非常重要，原因包括：

1. 代码版本可追踪  
2. 配置变更可回滚  
3. 换机器时可快速 clone  
4. 便于老师、同学或后续维护者复现环境  
5. 更接近真实软件项目的管理方式

因此，虽然本次运行不依赖重新 clone，但长期来看，仍建议把当前可运行版本纳入 Git 管理，并推送到远程仓库。

---

## 10. 本次任务中掌握的关键技术点

通过本次部署过程，实际掌握了以下内容：

- Linux 终端基本操作
- 项目目录结构理解
- Python 虚拟环境使用
- 脚本带参数运行
- 相对路径与工作目录的关系
- 日志重定向写法
- `systemd service` 的基本结构
- `cron` 的基本语法与定时任务配置
- 通过日志检查自动任务是否执行成功
- 区分本地 WSL 环境与远程服务器环境的差异

这些内容共同构成了一个完整的小型 Python 项目部署流程。

---

## 11. 本次任务的最终结论

本次任务已经成功完成了从“手动运行脚本”到“自动化运行任务”的整个过程。  
在本地 WSL Ubuntu 环境中，项目已实现：

- 成功运行主脚本
- 成功记录日志
- 成功使用 `systemd` 执行任务
- 成功使用 `cron` 实现每天早上 8 点自动运行

最终有效的定时任务配置为：

```cron
0 8 * * * cd /home/cardio_user/Test-cardio && /home/cardio_user/Test-cardio/.venv/bin/python src/cardio_twin_results_pipeline.py --config configs/config.yaml >> /home/cardio_user/Test-cardio/logs/cron.log 2>&1
```

因此，从课程任务和本地部署验证角度看，本次工作已经达到目标。

---

## 12. 后续改进建议

### 12.1 短期建议
保留当前本地可运行版本，不轻易破坏已经验证成功的环境。

### 12.2 中期建议
将当前项目整理进 Git/GitHub，形成更规范的版本管理流程。

### 12.3