"""Edit plan for Catherine Pang (洪記糖水, 第九屆參賽者).

Each phrase lists the words that are kept from the raw interview. Words are
matched against the force-aligned transcript (simplified Chinese, as the ASR
heard them, numbers written in Chinese), near an approximate source time, so
the cut points land exactly between syllables. Several pieces = in-phrase cuts
(stutters / filler removed). Only Catherine's answers are referenced; the
interviewer's questions and the crew chatter are never used.

Fields
  say   : [(approx_source_time, "words as heard"[, {"start": s, "end": e}]), ...]
          the optional dict pins a cut point by hand (false starts the ASR missed)
  text  : on-screen subtitle (Traditional Chinese, ASR mistakes corrected)
  kw    : keywords shown green + underlined
  zoom  : "wide" (base framing) | "close" (punch-in)
  fx    : effect on the cut into this phrase: glitch | shake | zoom
"""

PHRASES = [
    # ---------------- HOOK (taken from 3:09, moved to the top) ----------------
    dict(id="hook1", say=[(190.4, "很多人都觉得")], text="很多人都覺得", kw=[], zoom="wide"),
    dict(id="hook2", say=[(191.3, "创业很辛苦")], text="創業很辛苦", kw=["辛苦"], zoom="wide"),
    dict(id="hook3", say=[(192.1, "其实创业不辛苦的")], text="其實創業不辛苦的", kw=["不辛苦"], zoom="close", fx="glitch"),
    dict(id="hook4", say=[(193.5, "只是你要来到对的地方")], text="只是你要來到對的地方", kw=["對的地方"], zoom="close"),
    dict(id="hook5", say=[(195.4, "对的平台")], text="對的平台", kw=["對的平台"], zoom="close"),
    # ---------------- INTRO ----------------
    dict(id="intro1", say=[(31.6, "我是田大姐catherinepang")], text="我是甜大姐 Catherine Pang", kw=["甜大姐"], zoom="wide"),
    dict(id="intro2", say=[(35.1, "我本身是从事糖水行业")], text="我本身是從事糖水行業", kw=["糖水"], zoom="wide"),
    dict(id="intro3", say=[(37.5, "拥有自己的中央出发")], text="擁有自己的中央廚房", kw=["中央廚房"], zoom="wide"),
    # ---------------- WHY ----------------
    dict(id="why1", say=[(44.5, "我觉得创业才是我要的东西")], text="我覺得創業才是我要的東西", kw=["我要的東西"], zoom="close"),
    dict(id="why2", say=[(47.1, "因为"), (48.1, "我自己本身")], text="因為我自己本身", kw=[], zoom="close"),
    dict(id="why3", say=[(49.0, "不是那种早九晚五的"), (51.4, "乖乖派")], text="不是那種朝九晚五的乖乖派", kw=["乖乖派"], zoom="close"),
    # ---------------- STORY ----------------
    dict(id="st1", say=[(63.6, "我是第三次创业了")], text="我是第三次創業了", kw=["第三次"], zoom="wide", fx="zoom"),
    dict(id="st2", say=[(64.9, "我第一次创业的时候")], text="我第一次創業的時候", kw=[], zoom="wide"),
    dict(id="st3", say=[(66.0, "是我在刚刚要踏入三十岁的时候")], text="是我在剛剛要踏入30歲的時候", kw=["30歲"], zoom="wide"),
    dict(id="st4", say=[(69.0, "那时候我就进入了")], text="那時候我就進入了", kw=[], zoom="close"),
    dict(id="st5", say=[(70.5, "吉隆坡最大的批发市场")], text="吉隆坡最大的批發市場", kw=["最大的批發市場"], zoom="close"),
    dict(id="st6", say=[(72.5, "就批发来教")], text="就是批發辣椒", kw=["辣椒"], zoom="close"),
    dict(id="st7", say=[(105.5, "启动资金是不到五千块")], text="啟動資金是不到5000塊", kw=["5000塊"], zoom="wide"),
    dict(id="st8", say=[(76.3, "我刚刚好四十岁的时候")], text="我剛剛好40歲的時候", kw=["40歲"], zoom="wide"),
    dict(id="st9", say=[(78.9, "疫情就是从", {"start": 79.02}), (80.8, "最高峰的时候")], text="疫情，就是從最高峰的時候", kw=["最高峰"], zoom="wide"),
    dict(id="st10", say=[(81.8, "掉到最古顶")], text="掉到最谷底", kw=["最谷底"], zoom="close", fx="shake"),
    dict(id="st11", say=[(83.8, "四十一岁的时候再重新创业")], text="41歲的時候再重新創業", kw=["重新創業"], zoom="wide"),
    dict(id="st12", say=[(85.9, "为了还债")], text="為了還債", kw=["還債"], zoom="wide"),
    dict(id="st13", say=[(108.6, "第二次的时候是零的")], text="第二次的時候是零的", kw=["零"], zoom="close"),
    dict(id="st14", say=[(110.9, "是负债累累的")], text="是負債累累的", kw=["負債累累"], zoom="close"),
    dict(id="st15", say=[(89.4, "起起跌跌也大了很多的坑之后")], text="起起跌跌也踩了很多的坑之後", kw=["很多的坑"], zoom="wide"),
    dict(id="st17", say=[(92.8, "我是在四十五岁"), (95.6, "的时候才开始创业")], text="我是在45歲的時候才開始創業", kw=["45歲"], zoom="close"),
    # ---------------- INSIGHT ----------------
    dict(id="in1", say=[(175.6, "天下没有白走的路")], text="天下沒有白走的路", kw=["白走的路"], zoom="wide", fx="zoom"),
    dict(id="in2", say=[(177.2, "每一走的一步都算数")], text="每走的一步都算數", kw=["都算數"], zoom="wide"),
    dict(id="in3", say=[(197.0, "为什么我会参加")], text="為什麼我會參加", kw=[], zoom="close"),
    dict(id="in4", say=[(198.2, "第九届的"), (199.5, "圆梦创业大赛")], text="第九屆的圓夢創業大賽", kw=["圓夢創業大賽"], zoom="close"),
    dict(id="in5", say=[(200.9, "因为我来这边")], text="因為我來這邊", kw=[], zoom="wide"),
    dict(id="in6", say=[(201.8, "我找到我要的资源")], text="我找到我要的資源", kw=["資源"], zoom="wide"),
    dict(id="in7", say=[(203.2, "找到了我要的平台")], text="找到了我要的平台", kw=["平台"], zoom="wide"),
    dict(id="in8", say=[(204.6, "再加上有一", {"end": 205.24}), (206.0, "群都是在创业", {"start": 205.93})], text="再加上有一群都是在創業", kw=[], zoom="close"),
    dict(id="in9", say=[(207.2, "大家都是很正能量")], text="大家都是很正能量", kw=["正能量"], zoom="close"),
    dict(id="in10", say=[(208.5, "互相扶持的")], text="互相扶持的", kw=["互相扶持"], zoom="close"),
    # ---------------- MESSAGE ----------------
    dict(id="msg1", say=[(210.9, "有一句话"), (211.9, "想送给大家")], text="有一句話想送給大家", kw=[], zoom="wide"),
    dict(id="msg2", say=[(215.0, "最重要是你肯熬过去")], text="最重要是你肯熬過去", kw=["熬過去"], zoom="wide"),
    dict(id="msg3", say=[(217.3, "因为熬过的苦")], text="因為熬過的苦", kw=["苦"], zoom="close"),
    dict(id="msg4", say=[(219.8, "你才会觉得苦中的甜")], text="你才會覺得苦中的甜", kw=["苦中的甜"], zoom="close"),
    dict(id="msg5", say=[(221.5, "才是最甜")], text="才是最甜", kw=["最甜"], zoom="close", fx="glitch"),
    # ---------------- CTA ----------------
    dict(id="cta1", say=[(249.8, "希望在来临的第十一届")], text="希望在來臨的第十一屆", kw=["第十一屆"], zoom="wide"),
    dict(id="cta2", say=[(253.2, "圆梦工厂创业大赛里面见到你")], text="圓夢工場創業大賽裡面見到你", kw=["圓夢工場創業大賽"], zoom="wide"),
    dict(id="cta3", say=[(255.6, "我们一起互相加油", {"end": 257.38})], text="我們一起互相加油", kw=["加油"], zoom="close"),
]
