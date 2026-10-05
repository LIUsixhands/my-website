#!/usr/bin/env python3
"""sixhands.tw DNS 生效檢查。

用法：python3 .claude/scripts/dns_check_sixhands.py
需要：pip install dnspython

目標設定（2026-10-05 存入網路中文 DNS 代管）：
    sixhands.tw        A      -> 75.2.60.5                      (Netlify 負載平衡器)
    www.sixhands.tw    CNAME  -> sixhands-studio.netlify.app

注意：本執行環境的 DNS 查詢會被導向單一解析器，無法直接問權威伺服器，
所以這支程式看到的就是「全世界看到的」，沒有捷徑。
"""
import datetime, sys
try:
    import dns.resolver
except ImportError:
    sys.exit("請先執行：pip install dnspython")

WANT_A = "75.2.60.5"
WANT_CNAME = "sixhands-studio.netlify.app."

def q(name, rtype):
    try:
        return [x.to_text() for x in dns.resolver.resolve(name, rtype)]
    except Exception as e:
        return [f"__ERR__{type(e).__name__}"]

print(f"查詢時間 {datetime.datetime.utcnow():%Y-%m-%d %H:%M} UTC")
a   = q("sixhands.tw", "A")
cn  = q("www.sixhands.tw", "CNAME")
ok_a  = WANT_A in a
ok_cn = any(c.lower() == WANT_CNAME for c in cn)

print(f"  sixhands.tw      A     -> {a}   {'✅' if ok_a else '❌ 尚未生效'}")
print(f"  www.sixhands.tw  CNAME -> {cn}  {'✅' if ok_cn else '❌ 尚未生效'}")

if ok_a and ok_cn:
    print("\n✅ DNS 已生效。下一步：助哥到 Netlify 後台 Domain management 加入")
    print("   sixhands.tw 與 www.sixhands.tw，設 primary domain，SSL 會自動申請。")
else:
    print("\n⏳ 尚未生效。網路中文明載需 12–24 小時，且部分域名需管理局審核。")
    print("   SERVFAIL／NoNameservers = 還沒生效，不等於填錯。")
