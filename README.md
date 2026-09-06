# HypoWeaver-Qwen 代码与部署交付包

本包用于项目评审、系统部署和实验复核，包含当前工作目录中的后端与前端源码、提示模板、知识处理模块、测试、Docker 配置、公开案例数据和实验结果。未包含开发机密钥、私人数据库、已安装依赖和受限文献全文。

## 从这里开始

1. 完整部署：阅读 [README_DEPLOYMENT.md](README_DEPLOYMENT.md)。默认提供明确标注的公开启动样例；填入自己的百炼凭证后可使用在线模型。
2. 实验复核：阅读 [README_REPRODUCE.md](README_REPRODUCE.md)。两类公开实证案例的数据已附，可独立复算。
3. 代码定位：阅读 [CODE_MAP.md](CODE_MAP.md)。关键实现保留可编辑源文件，不以截图代替代码。
4. 交付验收：阅读 [VALIDATION.md](VALIDATION.md)。该文件明确区分实际通过的检查与未执行的检查。
5. 数据及第三方说明：阅读 [DATA_AND_LICENSES.md](DATA_AND_LICENSES.md)。

解压后先校验文件，命令只使用 Python 标准库，不访问网络：

```bash
python tools/verify_package.py
```

## 目录

| 目录或文件 | 内容 |
|---|---|
| backend/ | FastAPI 工作流、Qwen 适配器、知识服务、统计引擎、提示模板和后端测试 |
| frontend/ | React + TypeScript + Vite 工作台源码与前端测试 |
| src/、schemas/、samples/、tests/ | 上游证据处理、图谱、检索、发现模块及契约测试 |
| scripts/experiments/ | 系统能力、组件消融、Qwen-VL、空气质量及碳市场案例脚本 |
| scripts/research/ | 数据源、检索包、证据覆盖与图谱构建脚本 |
| experiments/ | 冻结协议与公开案例数据；包括原始文件及最小分析抽取 |
| output/experiments/ | 供核验的历史结果、统计表、图形、匿名调用回执与公开派生记录 |
| knowledge-data/ | 项目自编的公开启动说明样例，明确不等于历史实验知识库 |
| tools/ | 初始化配置、完整性校验与离线复核的统一入口 |
| docs/ | 数据契约、实验说明、来源快照、打包修改及脱敏记录 |
| Dockerfile、Dockerfile.knowledge、docker-compose.yml | 三服务构建与部署配置 |
| PACKAGE_MANIFEST.json、SHA256SUMS.txt | 本交付包实际文件的校验清单 |

## 复现范围

- **可直接复核：** 公开实证数据、统计结果、两类案例独立复算、六项系统指标及六次正式表格抽取结果。
- **需要自己的账号：** 新的百炼在线调用；包内没有 API key，历史调用回执不能作为账号凭证使用。
- **需要另行获授权的资产：** 与历史系统实验完全相同的全文知识快照。原快照标注 `authenticated_internal_research_only`，没有放入面向网盘提交的代码包。公开样例不能用于宣称重现论文中的在线性能。

本包保留当前尚未提交到 Git 的源码修改；源提交标识与逐文件来源哈希见 `docs/SOURCE_SNAPSHOT.json`。提交包额外修改仅针对路径迁移、默认本机端口绑定、配置初始化和交付验证，见 `docs/PACKAGING_CHANGES.json`。本包没有新增或代替作者作出开源许可证授权。
