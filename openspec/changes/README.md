# openspec/changes

变更提案目录。任何对规范的修改都必须先在这里留下提案，再改 `../specs/`，最后才改代码。

## 提案文件命名

```
<日期>-<短名>.md        例：2026-11-19-add-combo-key.md
```

## 提案模板

```markdown
# <变更标题>

## 背景 / 动机
为什么要改，解决什么问题。

## 影响面
- 涉及 capability：device-input / state-model / key-mapping / action-execution / learn-mode / terminal-ui
- 涉及模块与文件：
- 是否影响已有术语或状态字段：

## 规范变更
## ADDED Requirements
### Requirement: ...
#### Scenario: ...

## MODIFIED Requirements
### Requirement: <原名>
（原文 → 新文，说明差异）

## REMOVED Requirements
### Requirement: <原名>
（删除理由）

## 兼容性
对已有配置 / 已有行为的影响，是否需要迁移。

## 代码落地清单
改哪些模块、需要补哪些测试。

## 状态
待评审 / 已批准 / 已落地 / 已废弃
```

## 当前进行中的提案

（暂无）
