# 风格档案 Style Profiles

这里保存「已经整理过的剪辑风格」。每个风格是一个独立的 YAML 文件，由
`studio/style/profiles.py` 读写。

## 目前状态

目录中的 7 个文件（Fast_Paced_Interview、Premium_Brand_Story、Modern_Cinematic、
Playful_Motion_Graphics、Meta_Lead_Generation、Event_Promotion、Product_Sales_Ad）
**只是初始分类**（`category_only: true`），里面没有任何分析数据，**不代表已经分析出实际风格**，
也不能被任何项目当作标准使用。

## 审核状态

| 状态 | 含义 | 能否作为品牌标准 |
|---|---|---|
| `UNREVIEWED` | 自动分析产生，尚未有人确认 | 否 |
| `REFERENCE_ONLY` | 可以参考，但不是标准 | 否 |
| `REJECTED` | 已确认不要使用 | 否 |
| `APPROVED` | 审核人确认的风格标准 | **是** |

只有 `APPROVED` 的风格会被 `get_brand_standard()` 返回。分析程序产生的风格**永远**从
`UNREVIEWED` 开始，系统不会自动批准任何风格。

## 工作流程

1. 只选择**已经确认获得认可**的影片作为参考（不要因为影片在 Drive 里就当作好作品）。
2. 运行风格分析：
   ```python
   from studio.style.analyzer import analyze_video, write_style_report
   a = analyze_video("workspace/refs/approved_ad.mp4")
   md, js = write_style_report(a, "workspace/style_reports")
   ```
3. 打开 `*_style.md`，检查「A. 自动量测」的数据，并回答「C. 需要人工判断」的问题。
4. 由分析结果建立风格档案（状态为 UNREVIEWED）：
   ```python
   import json
   from studio.style.profiles import create_profile_from_analysis
   create_profile_from_analysis(json.loads(open(js).read()), "DFSC_Interview_2026", use_cases=["人物采访"])
   ```
5. 审核人决定状态（必须填写审核人名字，会写入 `history`）：
   ```python
   from studio.style.profiles import set_review_status
   set_review_status("DFSC_Interview_2026", "APPROVED", reviewer="审核人名字", note="与 2026 招生广告一致")
   ```
6. 每次修改都会追加到 `history`，可以追溯谁在什么时候改了什么。

## 每个档案记录的内容

风格名称、来源视频、参考时间码、关键画面、动画参数、剪辑参数、视觉参数、音频参数、
适用场景、审核状态、修改历史、相关代码、参考截图、使用该风格的项目。
