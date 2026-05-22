const fs = require("fs");
const path = require("path");

const base = path.resolve(__dirname, "..");
const labels = {
  "financial-news": "金融消息",
  "earnings-search": "财报搜集",
  "stock-crypto-fundamentals": "个股/币种基本面",
  "sector-trend-data": "板块走势数据",
  "sector-trend-us-close-review": "美股收盘复查",
  "sector-rotation": "板块轮动",
  "earnings-vertical-compare": "财报纵向对比",
  "us-sector-opportunity": "美股机会洞察",
};

const fallbackCron = `0 19 * * * /root/codex-automations/run.sh financial-news
*/10 19-21 * * * /root/codex-automations/run-if-missed.sh financial-news 19:00 '*' 180

0 23 * * 2-6 /root/codex-automations/run.sh earnings-search
*/10 23 * * 2-6 /root/codex-automations/run-if-missed.sh earnings-search 23:00 2,3,4,5,6 59

0 8 * * 2-6 /root/codex-automations/run.sh stock-crypto-fundamentals
*/10 8-10 * * 2-6 /root/codex-automations/run-if-missed.sh stock-crypto-fundamentals 08:00 2,3,4,5,6 180

30 8 * * * /root/codex-automations/run.sh sector-trend-data
*/10 8-11 * * * /root/codex-automations/run-if-missed.sh sector-trend-data 08:30 '*' 180

0 10 * * 2-6 /root/codex-automations/run.sh sector-trend-us-close-review
*/10 10-12 * * 2-6 /root/codex-automations/run-if-missed.sh sector-trend-us-close-review 10:00 2,3,4,5,6 180

30 10 * * 2-6 /root/codex-automations/run.sh sector-rotation
*/10 10-13 * * 2-6 /root/codex-automations/run-if-missed.sh sector-rotation 10:30 2,3,4,5,6 180

0 12 * * 2-6 /root/codex-automations/run.sh earnings-vertical-compare
*/10 12-14 * * 2-6 /root/codex-automations/run-if-missed.sh earnings-vertical-compare 12:00 2,3,4,5,6 180

0 13 * * 2-6 /root/codex-automations/run.sh us-sector-opportunity
*/10 13-15 * * 2-6 /root/codex-automations/run-if-missed.sh us-sector-opportunity 13:00 2,3,4,5,6 180`;

function readText(file) {
  try {
    return fs.readFileSync(path.join(base, file), "utf8");
  } catch {
    return "";
  }
}

function humanCronTime(minute, hour, dow) {
  const days = dow === "*" ? "每天" : dow === "2-6" ? "周二至周六" : dow;
  return `${days} ${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function parseCron(text) {
  const jobs = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const parts = line.split(/\s+/);
    if (parts.length < 7) continue;
    const [minute, hour, , , dow, command] = parts;
    if (command.endsWith("/run.sh") && parts[6]) {
      const job = parts[6];
      jobs[job] ||= {};
      jobs[job].schedule = {
        minute,
        hour,
        dow,
        raw: line,
        label: humanCronTime(minute, hour, dow),
      };
    }
    if (command.endsWith("/run-if-missed.sh") && parts[6]) {
      const job = parts[6];
      jobs[job] ||= {};
      jobs[job].catchup = {
        window_minutes: Number(parts[9]) || null,
        raw: line,
        label: `${parts[7]} 后 ${parts[9]} 分钟内每 10 分钟补跑`,
      };
    }
  }
  return jobs;
}

function nextRun(schedule, now) {
  if (!schedule || !/^\d+$/.test(schedule.minute) || !/^\d+$/.test(schedule.hour)) return null;
  let allowed = new Set([1, 2, 3, 4, 5, 6, 7]);
  if (schedule.dow === "2-6") allowed = new Set([2, 3, 4, 5, 6]);
  for (let i = 0; i < 14; i += 1) {
    const candidate = new Date(now);
    candidate.setDate(now.getDate() + i);
    candidate.setHours(Number(schedule.hour), Number(schedule.minute), 0, 0);
    const jsDay = candidate.getDay();
    const isoDay = jsDay === 0 ? 7 : jsDay;
    if (candidate > now && allowed.has(isoDay)) return candidate.toISOString();
  }
  return null;
}

module.exports = function handler(req, res) {
  const now = new Date();
  const cron = readText("crontab.with-catchup") || fallbackCron;
  const cronJobs = parseCron(cron);
  const jobs = Object.keys({ ...labels, ...cronJobs }).sort().map((job) => {
    const promptPath = path.join(base, "prompts", `${job}.md`);
    const schedule = cronJobs[job]?.schedule || null;
    return {
      job,
      label: labels[job] || job,
      status: "idle",
      schedule,
      catchup: cronJobs[job]?.catchup || null,
      next_run: nextRun(schedule, now),
      done_today: false,
      done_marker: "Not available on Vercel",
      prompt_exists: fs.existsSync(promptPath),
      log_exists: false,
      log_path: "Local logs are not available on Vercel",
      last_start: null,
      last_done: null,
      duration_seconds: null,
      retry_count: 0,
      skipped_count: 0,
      last_validation: {
        status: "readonly",
        detail: "Vercel deployment can show configuration only; live logs/state are available on the local dashboard.",
      },
      notion_pages: [],
      config_warning: false,
      hard_error: false,
      tail: [
        "Vercel read-only mode.",
        "This deployment cannot access /root/codex-automations logs, state markers, or local crontab.",
        "Use the local dashboard for live runtime status.",
      ],
    };
  });

  res.setHeader("Cache-Control", "no-store");
  res.status(200).json({
    now: now.toISOString(),
    cron_in_sync: true,
    deployment_mode: "vercel-readonly",
    jobs,
  });
};
