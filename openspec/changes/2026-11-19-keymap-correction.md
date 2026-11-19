# 2026-11-19 按键口径修正（依据官方说明书 + 实测）

## Why

官方操作说明与实测表明：本耳机共 **4 颗物理键**（电源 / ＋ / − / 通话），
**没有独立静音键**；且绝大部分手势走 AVRCP / HFP，不进入 macOS 事件流。

## What changes

1. `mute:click` 的物理来源改为「通话中电源键单击」，UI 标注「系统独占」。
2. `volp:long` / `volm:long` 语义为「＋/− 长按 = 上一曲 / 下一曲」，不再是按住说话。
3. 新增待验证项：AVRCP Next/Prev、Play/Pause 是否可被观测；通过后增加 `power:click` 触发源。
4. 通话键三手势在非通话态不产出任何事件（禁止软件伪造）。

## Impact

- spec：`openspec/specs/device-input/spec.md`（静音键来源注释）、`clearcall200/vol_watch.py`（唯一生效采集通道）
- 文档：新增 `docs/按键功能对照.md`
- UI：卡片需标注可用性（通话键 = 仅通话中；电源键 = 播放/暂停）
