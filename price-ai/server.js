// 小登實價AI — Claude × 內政部實價登錄 成交行情分析助理（Sixhands Studio 實登行情數據官）
// 啟動：npm start，然後打開 http://localhost:3000

import "dotenv/config";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Anthropic from "@anthropic-ai/sdk";
import { betaTool } from "@anthropic-ai/sdk/helpers/beta/json-schema";
import { searchRealPrice, CITY_CODES, recentSeasons } from "./moi-data.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 3000;
const MODEL = process.env.CLAUDE_MODEL || "claude-opus-4-8";

const client = new Anthropic(); // 讀取環境變數 ANTHROPIC_API_KEY
const ACCESS_CODE = process.env.ACCESS_CODE || null; // 選填：設定後才需要通關密碼

// ---------- 給 Claude 使用的工具：查詢實價登錄 ----------
const realPriceTool = betaTool({
  name: "search_real_price",
  description:
    "查詢內政部實價登錄的不動產成交資料，回傳統計數據（平均/中位數總價、每坪單價）與最新成交明細。" +
    "當使用者詢問任何地區的房價行情、成交價、租金行情、預售屋價格時，一定要呼叫這個工具，不要憑記憶回答。" +
    "若要比較多個行政區或多種條件，可以分次呼叫多次。",
  inputSchema: {
    type: "object",
    properties: {
      city: {
        type: "string",
        description: `縣市名稱，例如「臺中市」。支援：${Object.keys(CITY_CODES).filter(k => !k.startsWith("台")).join("、")}`,
      },
      district: {
        type: "string",
        description: "行政區，例如「北屯區」「西屯區」。不填則查全縣市並回傳各區分佈。",
      },
      deal_type: {
        type: "string",
        enum: ["買賣", "預售屋", "租賃"],
        description: "交易類別，預設「買賣」（中古+新成屋成交）。",
      },
      keyword: {
        type: "string",
        description: "地址關鍵字，例如路名「文心路」或重劃區相關路段。",
      },
      building_type: {
        type: "string",
        description: "建物型態關鍵字，例如「住宅大樓」「華廈」「透天厝」「套房」「公寓」。",
      },
      min_total_price_wan: { type: "number", description: "總價下限（萬元）" },
      max_total_price_wan: { type: "number", description: "總價上限（萬元）" },
      season: {
        type: "string",
        description: `指定資料季別（民國年+季），例如「114S4」。不填則自動使用最新一季。目前最近季別：${recentSeasons(4).join("、")}`,
      },
      limit: { type: "number", description: "回傳明細筆數上限，預設 15，最多 30。" },
    },
    required: [],
  },
  run: async (input) => {
    try {
      const result = await searchRealPrice(input);
      return JSON.stringify(result);
    } catch (e) {
      return JSON.stringify({ 錯誤: e.message });
    }
  },
});

const SYSTEM_PROMPT = `你是「小登」（全名「小登實價AI」），Sixhands Studio 的實登行情數據官——一位台灣不動產成交行情分析助理，資料來源是內政部實價登錄開放資料。自稱時用「小登」。

規則：
1. 只要問題涉及行情、價格、成交、租金，一定先呼叫 search_real_price 工具取得真實資料，再根據資料回答，絕不憑印象編造數字。
2. 需要比較（不同行政區、不同建物型態、不同價格帶）時，分別呼叫工具多次再彙整。
3. 金額一律用台灣習慣表示：總價用「萬元」，單價用「萬元/坪」。
4. 回答結構：先給重點結論（1-2 句），再列統計數據，需要時附上代表性成交案例（地址、日期、總價、單價、格局）。
5. 分析時注意：實價登錄的「備註」欄可能標示親友交易、含增建等特殊情況；單價異常高低的案件要提醒可能是特殊交易。預售屋與中古屋行情要分開看。
6. 資料為季度批次公開，最新一季可能尚不完整，回答時註明資料季別。
7. 用繁體中文、口語但專業的語氣回答。結尾附一行小字提醒：「資料來源：內政部實價登錄，僅供參考，實際成交以個案為準。」
8. 若使用者的問題與不動產無關，簡短說明小登的專長是實價登錄行情查詢。`;

// ---------- HTTP 伺服器 ----------
const app = express();
app.use(express.json({ limit: "1mb" }));
app.use(express.static(path.join(__dirname, "public")));

app.post("/api/verify-code", (req, res) => {
  if (!ACCESS_CODE) return res.json({ ok: true });
  const code = typeof req.body?.code === "string" ? req.body.code : "";
  if (code === ACCESS_CODE) return res.json({ ok: true });
  res.status(401).json({ ok: false, error: "通關密碼錯誤" });
});

app.post("/api/chat", async (req, res) => {
  if (ACCESS_CODE && req.headers["x-access-code"] !== ACCESS_CODE) {
    return res.status(401).json({ error: "請先輸入正確的通關密碼" });
  }

  const history = Array.isArray(req.body?.messages) ? req.body.messages : [];
  const messages = history
    .filter(m => (m.role === "user" || m.role === "assistant") && typeof m.content === "string" && m.content.trim())
    .slice(-20)
    .map(m => ({ role: m.role, content: m.content }));

  if (!messages.length || messages[messages.length - 1].role !== "user") {
    return res.status(400).json({ error: "請提供訊息內容" });
  }

  if (!process.env.ANTHROPIC_API_KEY) {
    return res.status(500).json({
      error: "尚未設定 API 金鑰。請把 .env.example 複製成 .env，填入 ANTHROPIC_API_KEY 後重新啟動。",
    });
  }

  try {
    const finalMessage = await client.beta.messages.toolRunner({
      model: MODEL,
      max_tokens: 16000,
      thinking: { type: "adaptive" },
      system: SYSTEM_PROMPT,
      tools: [realPriceTool],
      messages,
      max_iterations: 8,
    });

    const text = finalMessage.content
      .filter(b => b.type === "text")
      .map(b => b.text)
      .join("\n");

    res.json({ reply: text || "（沒有產生回覆，請再試一次）" });
  } catch (error) {
    if (error instanceof Anthropic.AuthenticationError) {
      res.status(500).json({ error: "API 金鑰無效，請檢查 .env 裡的 ANTHROPIC_API_KEY。" });
    } else if (error instanceof Anthropic.RateLimitError) {
      res.status(429).json({ error: "請求太頻繁，請稍後再試。" });
    } else if (error instanceof Anthropic.APIConnectionError) {
      res.status(502).json({ error: "無法連線到 Claude API，請檢查網路。" });
    } else if (error instanceof Anthropic.APIError) {
      res.status(500).json({ error: `Claude API 錯誤（${error.status}）：${error.message}` });
    } else {
      console.error(error);
      res.status(500).json({ error: `伺服器錯誤：${error.message}` });
    }
  }
});

app.listen(PORT, () => {
  console.log(`✅ 小登實價AI 已啟動：http://localhost:${PORT}`);
  console.log(`   模型：${MODEL}`);
  if (!process.env.ANTHROPIC_API_KEY) {
    console.warn("⚠️  尚未設定 ANTHROPIC_API_KEY，請建立 .env 檔（參考 .env.example）");
  }
});
