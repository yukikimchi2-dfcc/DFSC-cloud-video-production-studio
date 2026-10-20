"""On-screen graphics for the Catherine Pang cut (reference: Dream Factory / AK video).

Anchors:  "<phrase>"        phrase start
          "<phrase>:<字>"   the moment that character is spoken (subtitle reveal)
          "<phrase>.end"    phrase end
          a "+0.2" / "-0.1" suffix shifts the anchor in seconds
Text:     "[...]" marks green (keyword) text inside a box.

Types
  header   small navy box with two text groups (hook title)       -> like 創業之前 先聽這句
  box      navy / green / tag box; size L(110) M(64) S(46)        -> like 沒有認知, 短期內 + 達到認知
  serif    big serif word with glitch-in and gold sparkles        -> like 不簡單 / 極高 / 等你來挑戰
  name     name card: green box + white tag + two stickers        -> like AK 關德輝 / 演員・歌手
  rows     stacked small navy rows with an icon and a final tick  -> like Due Diligence / Compliance
"""

TITLES = [
    # ---------------- hook ----------------
    dict(type="header", start="hook1-1", end="hook2:辛+0.15", left="創業之前", right="先聽這句", emoji="👂"),
    dict(type="box", start="hook2:辛-0.2", end="hook3", text="創業很[辛苦]", style="navy", size="L", cy=372, emoji="😩"),
    dict(type="serif", start="hook3:不-0.05", end="hook4:對", text="不辛苦", fill="white", emoji="😎", sfx="impact"),
    dict(type="box", start="hook4:對-0.1", end="hook5.end", text="對的地方", style="navy", size="S", cy=255),
    dict(type="box", start="hook5", end="hook5.end", text="對的平台", style="green", size="L", cy=420, emoji="💡"),
    # ---------------- intro ----------------
    dict(type="name", start="intro1", end="intro3.end", name="Catherine Pang", tag="洪記糖水 ・ 第九屆參賽者",
         left="🍧", right="🏆"),
    # ---------------- why ----------------
    dict(type="box", start="why1:創", end="why1.end", text="創業才是[我要的]", style="navy", size="L", cy=372, emoji="🎯"),
    dict(type="box", start="why3:朝-0.1", end="why3.end", text="朝九晚五", style="navy", size="S", cy=255),
    dict(type="box", start="why3:乖-0.1", end="why3.end", text="[不是]乖乖派", style="tag", size="M", cy=380, emoji="🙅"),
    # ---------------- story ----------------
    dict(type="box", start="st1:第", end="st1.end", text="第三次創業", style="green", size="L", cy=372, emoji="🔥"),
    dict(type="box", start="st2:第", end="st3.end", text="第一次創業", style="navy", size="S", cy=255),
    dict(type="box", start="st3:3", end="st3.end", text="[30歲]", style="navy", size="L", cy=420, emoji="🌱"),
    dict(type="box", start="st5:吉", end="st6.end", text="吉隆坡最大的批發市場", style="navy", size="S", cy=255),
    dict(type="box", start="st6:批", end="st6.end", text="批發[辣椒]", style="green", size="L", cy=420, emoji="🌶"),
    dict(type="box", start="st7:啟", end="st7.end", text="第一次啟動資金", style="navy", size="S", cy=255),
    dict(type="box", start="st7:不", end="st7.end", text="不到[5000塊]", style="navy", size="L", cy=420, emoji="💰"),
    dict(type="box", start="st8:4", end="st9.end", text="40歲", style="navy", size="S", cy=255),
    dict(type="box", start="st9:疫", end="st9.end", text="一場[疫情]", style="navy", size="L", cy=420, emoji="😷"),
    dict(type="serif", start="st10:掉-0.05", end="st10.end+0.25", text="掉到最谷底", fill="white", emoji="📉", sfx="impact"),
    dict(type="box", start="st11:重", end="st12.end", text="41歲 重新創業", style="navy", size="S", cy=255),
    dict(type="box", start="st12:還-0.1", end="st12.end", text="為了[還債]", style="navy", size="L", cy=420, emoji="💸"),
    dict(type="box", start="st13:二", end="st13.end", text="啟動資金：零", style="tag", size="M", cy=372),
    dict(type="serif", start="st14:負-0.05", end="st14.end+0.2", text="負債累累", fill="white", emoji="💸", sfx="impact"),
    dict(type="box", start="st15:起", end="st15.end", text="起起跌跌", style="navy", size="S", cy=255),
    dict(type="box", start="st15:坑-0.15", end="st15.end", text="踩了很多[坑]", style="navy", size="L", cy=420, emoji="🕳"),
    dict(type="box", start="st17:4", end="st17.end", text="45歲 正式創業", style="green", size="L", cy=372, emoji="🚀"),
    # ---------------- insight ----------------
    dict(type="box", start="in1:白-0.1", end="in2.end", text="沒有[白走]的路", style="navy", size="L", cy=330, emoji="🛤", emoji_side="left"),
    dict(type="box", start="in2:一-0.1", end="in2.end", text="每一步都[算數]", style="navy", size="L", cy=520, emoji="👣"),
    dict(type="box", start="in4:第", end="in4.end", text="第九屆", style="navy", size="S", cy=255),
    dict(type="box", start="in4:圓-0.1", end="in4.end", text="圓夢工場・創業大賽", style="green", size="L", cy=420, emoji="🏆"),
    dict(type="rows", start="in6:資-0.2", end="in10.end", icon="📋", check_at="in10:互",
         rows=[("in6:資-0.2", "找到[資源]"), ("in7:平-0.2", "找到[平台]"), ("in9:正-0.2", "[正能量] 互相扶持")]),
    # ---------------- message ----------------
    dict(type="box", start="msg1:一", end="msg1.end", text="一句話送給大家", style="navy", size="L", cy=372, emoji="🎁"),
    dict(type="box", start="msg2:熬-0.1", end="msg3.end", text="肯[熬過去]", style="green", size="L", cy=372, emoji="💪"),
    dict(type="serif", start="msg4:苦-0.05", end="msg4.end", text="苦中的甜", fill="white", emoji="🍧", sfx="impact"),
    dict(type="serif", start="msg5:才-0.02", end="msg5.end+0.1", text="才是最甜", fill="green", emoji="✨", sfx="impact"),
    # ---------------- CTA ----------------
    dict(type="box", start="cta1:第", end="cta2.end", text="第十一屆", style="navy", size="S", cy=255),
    dict(type="box", start="cta2:圓-0.1", end="cta2.end", text="圓夢工場・創業大賽", style="green", size="L", cy=420),
    dict(type="serif", start="cta3:一-0.05", end="cta3.end+0.4", text="一起加油", fill="green", emoji="🔥",
         emoji_side="left", emoji2="💪", sfx="impact"),
]
