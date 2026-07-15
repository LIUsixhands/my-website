// 內政部實價登錄開放資料模組
// 資料來源：內政部不動產成交案件實際資訊資料供應系統（plvr.land.moi.gov.tw）
// 每季一個 CSV 檔，網址格式：
//   https://plvr.land.moi.gov.tw/DownloadSeason?season={民國年}S{季}&fileName={縣市代碼}_lvr_land_{類別}.csv
// 類別：A=不動產買賣、B=預售屋買賣、C=不動產租賃

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CACHE_DIR = path.join(__dirname, "cache");

export const CITY_CODES = {
  臺北市: "A", 台北市: "A",
  臺中市: "B", 台中市: "B",
  基隆市: "C",
  臺南市: "D", 台南市: "D",
  高雄市: "E",
  新北市: "F",
  宜蘭縣: "G",
  桃園市: "H",
  嘉義市: "I",
  新竹縣: "J",
  苗栗縣: "K",
  南投縣: "M",
  彰化縣: "N",
  新竹市: "O",
  雲林縣: "P",
  嘉義縣: "Q",
  屏東縣: "T",
  花蓮縣: "U",
  臺東縣: "V", 台東縣: "V",
  金門縣: "W",
  澎湖縣: "X",
  連江縣: "Z",
};

export const DEAL_TYPES = {
  買賣: "A",
  預售屋: "B",
  租賃: "C",
};

const PING = 3.305785; // 1 坪 = 3.305785 平方公尺

// ---------- CSV 解析（處理引號內含逗號、換行的欄位，例如「備註」欄） ----------
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else field += c;
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      row.push(field); field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.length > 1 || row[0] !== "") rows.push(row);
      row = [];
    } else {
      field += c;
    }
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  return rows;
}

// ---------- 季別計算 ----------
// 回傳最近 n 個季別字串（民國年），由新到舊，例如 ["115S2","115S1","114S4",...]
export function recentSeasons(n = 6) {
  const now = new Date();
  let rocYear = now.getFullYear() - 1911;
  let quarter = Math.ceil((now.getMonth() + 1) / 3);
  const seasons = [];
  for (let i = 0; i < n; i++) {
    seasons.push(`${rocYear}S${quarter}`);
    quarter--;
    if (quarter === 0) { quarter = 4; rocYear--; }
  }
  return seasons;
}

// ---------- 下載 + 快取 ----------
async function fetchSeasonCsv(cityCode, season, dealType) {
  const cacheFile = path.join(CACHE_DIR, `${season}_${cityCode}_${dealType}.csv`);
  if (fs.existsSync(cacheFile)) {
    return fs.readFileSync(cacheFile, "utf8");
  }
  const url = `https://plvr.land.moi.gov.tw/DownloadSeason?season=${season}&fileName=${cityCode}_lvr_land_${dealType}.csv`;
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (shijia-ai; real-price data client)" },
  });
  if (!res.ok) throw new Error(`下載失敗 HTTP ${res.status}（${season}）`);
  const text = await res.text();
  // 網站對不存在的季別有時回傳空檔或 HTML 錯誤頁
  if (!text || text.length < 200 || text.trimStart().startsWith("<")) {
    throw new Error(`該季別尚無資料（${season}）`);
  }
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  fs.writeFileSync(cacheFile, text, "utf8");
  return text;
}

// ---------- 轉成物件陣列 ----------
function toRecords(csvText) {
  const rows = parseCsv(csvText.replace(/^﻿/, ""));
  if (rows.length < 3) return [];
  const headers = rows[0]; // 第一列中文欄名；第二列是英文欄名，跳過
  const records = [];
  for (let i = 2; i < rows.length; i++) {
    const rec = {};
    headers.forEach((h, idx) => { rec[h] = rows[i][idx] ?? ""; });
    records.push(rec);
  }
  return records;
}

function num(v) {
  const n = parseFloat(String(v).replace(/,/g, ""));
  return Number.isFinite(n) ? n : 0;
}

// 民國日期字串 1130315 → "113/03/15"
function rocDate(v) {
  const s = String(v).trim();
  if (s.length < 6) return s;
  return `${s.slice(0, -4)}/${s.slice(-4, -2)}/${s.slice(-2)}`;
}

function median(arr) {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

const round1 = (n) => Math.round(n * 10) / 10;

// ---------- 主查詢函式（給 Claude 的工具呼叫） ----------
export async function searchRealPrice({
  city = "臺中市",
  district,
  deal_type = "買賣",
  keyword,
  building_type,
  min_total_price_wan,
  max_total_price_wan,
  season,
  limit = 15,
} = {}) {
  const cityCode = CITY_CODES[city.trim()] ?? CITY_CODES[city.trim().replace(/^台/, "臺")];
  if (!cityCode) throw new Error(`不支援的縣市：${city}。支援：${Object.keys(CITY_CODES).filter(k => k.startsWith("臺") || !k.startsWith("台")).join("、")}`);
  const typeCode = DEAL_TYPES[deal_type] ?? "A";

  // 指定季別就用指定的；否則從最新往回找到有資料的一季
  const seasonsToTry = season ? [season] : recentSeasons(6);
  let records = [];
  let seasonUsed = null;
  let lastErr = null;
  for (const s of seasonsToTry) {
    try {
      const csv = await fetchSeasonCsv(cityCode, s, typeCode);
      records = toRecords(csv);
      if (records.length > 0) { seasonUsed = s; break; }
    } catch (e) {
      lastErr = e;
    }
  }
  if (!seasonUsed) {
    throw new Error(`查無資料。${lastErr ? lastErr.message : ""}`);
  }

  // ---------- 篩選 ----------
  let filtered = records;
  if (district) {
    const d = district.trim().replace(/^台/, "臺");
    filtered = filtered.filter(r => (r["鄉鎮市區"] || "").includes(d) || (r["鄉鎮市區"] || "").includes(district.trim()));
  }
  if (keyword) {
    filtered = filtered.filter(r => (r["土地位置建物門牌"] || "").includes(keyword.trim()));
  }
  if (building_type) {
    filtered = filtered.filter(r => (r["建物型態"] || "").includes(building_type.trim()));
  }
  if (min_total_price_wan) {
    filtered = filtered.filter(r => num(r["總價元"]) >= min_total_price_wan * 10000);
  }
  if (max_total_price_wan) {
    filtered = filtered.filter(r => num(r["總價元"]) <= max_total_price_wan * 10000);
  }

  // ---------- 統計 ----------
  const totals = filtered.map(r => num(r["總價元"])).filter(n => n > 0);
  const unitPerPing = filtered
    .map(r => num(r["單價元平方公尺"]) * PING / 10000) // 萬元/坪
    .filter(n => n > 0);

  const isRent = typeCode === "C";
  const stats = {
    符合筆數: filtered.length,
    [isRent ? "平均月租金_萬元" : "平均總價_萬元"]: totals.length ? round1(totals.reduce((a, b) => a + b, 0) / totals.length / 10000) : null,
    [isRent ? "月租金中位數_萬元" : "總價中位數_萬元"]: totals.length ? round1(median(totals) / 10000) : null,
    [isRent ? "最低月租金_萬元" : "最低總價_萬元"]: totals.length ? round1(Math.min(...totals) / 10000) : null,
    [isRent ? "最高月租金_萬元" : "最高總價_萬元"]: totals.length ? round1(Math.max(...totals) / 10000) : null,
    平均單價_萬元每坪: unitPerPing.length ? round1(unitPerPing.reduce((a, b) => a + b, 0) / unitPerPing.length) : null,
    單價中位數_萬元每坪: unitPerPing.length ? round1(median(unitPerPing)) : null,
  };

  // ---------- 各區分佈（未指定行政區時，幫助整體比較） ----------
  let districtBreakdown = null;
  if (!district) {
    const byDistrict = new Map();
    for (const r of filtered) {
      const d = r["鄉鎮市區"] || "未知";
      if (!byDistrict.has(d)) byDistrict.set(d, { count: 0, unitSum: 0, unitN: 0 });
      const b = byDistrict.get(d);
      b.count++;
      const u = num(r["單價元平方公尺"]) * PING / 10000;
      if (u > 0) { b.unitSum += u; b.unitN++; }
    }
    districtBreakdown = [...byDistrict.entries()]
      .map(([d, b]) => ({ 行政區: d, 筆數: b.count, 平均單價_萬元每坪: b.unitN ? round1(b.unitSum / b.unitN) : null }))
      .sort((a, b) => b.筆數 - a.筆數)
      .slice(0, 15);
  }

  // ---------- 明細範例（依交易日期新到舊） ----------
  const sample = [...filtered]
    .sort((a, b) => num(b["交易年月日"]) - num(a["交易年月日"]))
    .slice(0, Math.min(limit, 30))
    .map(r => {
      const areaPing = num(r["建物移轉總面積平方公尺"]) / PING;
      const unit = num(r["單價元平方公尺"]) * PING / 10000;
      return {
        行政區: r["鄉鎮市區"],
        地址: r["土地位置建物門牌"],
        交易日期: rocDate(r["交易年月日"]),
        [isRent ? "月租金_萬元" : "總價_萬元"]: round1(num(r["總價元"]) / 10000),
        單價_萬元每坪: unit ? round1(unit) : null,
        建物面積_坪: areaPing ? round1(areaPing) : null,
        建物型態: r["建物型態"],
        格局: [r["建物現況格局-房"], r["建物現況格局-廳"], r["建物現況格局-衛"]].some(Boolean)
          ? `${r["建物現況格局-房"] || 0}房${r["建物現況格局-廳"] || 0}廳${r["建物現況格局-衛"] || 0}衛`
          : null,
        樓層: r["移轉層次"] ? `${r["移轉層次"]}/${r["總樓層數"] || "?"}` : null,
        屋齡參考_建築完成年月: r["建築完成年月"] ? rocDate(r["建築完成年月"]) : null,
        車位總價_萬元: num(r["車位總價元"]) ? round1(num(r["車位總價元"]) / 10000) : null,
        備註: (r["備註"] || "").slice(0, 60) || null,
      };
    });

  return {
    資料來源: "內政部實價登錄（不動產成交案件實際資訊資料供應系統）",
    縣市: city,
    交易類別: deal_type,
    季別: seasonUsed,
    篩選條件: { 行政區: district || "全部", 關鍵字: keyword || null, 建物型態: building_type || null },
    統計: stats,
    ...(districtBreakdown ? { 各行政區分佈: districtBreakdown } : {}),
    最新成交明細: sample,
  };
}
