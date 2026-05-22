const statusText = {
  passed: "通过",
  failed: "失败",
  warning: "警告",
  running: "运行中",
  idle: "待运行",
};

let state = null;
let selectedJob = null;

const fmt = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

function formatTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return fmt.format(date);
}

function formatDuration(seconds) {
  if (seconds == null) return "--";
  if (seconds < 60) return `${seconds}s`;
  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return `${min}m ${sec}s`;
}

function statusClass(status) {
  return `status ${status || "idle"}`;
}

async function loadStatus() {
  const response = await fetch("/api/status", { cache: "no-store" });
  state = await response.json();
  if (!selectedJob && state.jobs.length) selectedJob = state.jobs[0].job;
  render();
}

function renderMetrics(jobs) {
  const counts = jobs.reduce((acc, job) => {
    acc[job.status] = (acc[job.status] || 0) + 1;
    return acc;
  }, {});
  const metrics = [
    ["任务总数", jobs.length],
    ["今日通过", counts.passed || 0],
    ["运行中", counts.running || 0],
    ["失败", counts.failed || 0],
    ["警告", counts.warning || 0],
  ];
  document.querySelector("#metrics").innerHTML = metrics
    .map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
}

function renderTable(jobs) {
  document.querySelector("#job-count").textContent = `${jobs.length} jobs`;
  document.querySelector("#jobs").innerHTML = jobs
    .map((job) => {
      const validation = job.last_validation?.status || "--";
      const schedule = job.schedule?.label || "--";
      return `
        <tr data-job="${job.job}" class="${job.job === selectedJob ? "selected" : ""}">
          <td><span class="${statusClass(job.status)}">${statusText[job.status] || job.status}</span></td>
          <td><strong>${job.label}</strong><div class="muted">${job.job}</div></td>
          <td>${schedule}<div class="muted">${job.catchup?.label || "--"}</div></td>
          <td>${formatTime(job.last_done)}<div class="muted">${formatDuration(job.duration_seconds)}</div></td>
          <td>${validation}<div class="muted">${job.done_today ? "done marker" : "no marker"}</div></td>
          <td>${formatTime(job.next_run)}</td>
        </tr>
      `;
    })
    .join("");
  document.querySelectorAll("tr[data-job]").forEach((row) => {
    row.addEventListener("click", () => {
      selectedJob = row.dataset.job;
      render();
    });
  });
}

function renderDetail(job) {
  document.querySelector("#detail-title").textContent = job ? job.label : "详情";
  const detailStatus = document.querySelector("#detail-status");
  detailStatus.textContent = job ? (statusText[job.status] || job.status) : "--";
  detailStatus.className = `pill ${job?.status || ""}`;

  if (!job) {
    document.querySelector("#detail-meta").innerHTML = "";
    document.querySelector("#detail-links").innerHTML = "";
    document.querySelector("#log").textContent = "";
    return;
  }

  const validation = job.last_validation
    ? `${job.last_validation.status}: ${job.last_validation.detail || ""}`
    : "--";
  const meta = [
    ["Job", job.job],
    ["调度", job.schedule?.raw || "--"],
    ["补跑", job.catchup?.raw || "--"],
    ["下次", formatTime(job.next_run)],
    ["最近开始", formatTime(job.last_start)],
    ["最近完成", formatTime(job.last_done)],
    ["耗时", formatDuration(job.duration_seconds)],
    ["校验", validation],
    ["日志", job.log_path],
  ];
  document.querySelector("#detail-meta").innerHTML = meta
    .map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`)
    .join("");

  document.querySelector("#detail-links").innerHTML = (job.notion_pages || [])
    .map((url, index) => `<a href="${url}" target="_blank" rel="noreferrer">Notion ${index + 1}: ${url}</a>`)
    .join("");

  document.querySelector("#log").textContent = (job.tail || []).join("\n");
}

function render() {
  if (!state) return;
  const jobs = state.jobs;
  document.querySelector("#clock").textContent = `更新时间 ${formatTime(state.now)}`;
  const sync = document.querySelector("#sync");
  sync.textContent = state.cron_in_sync ? "crontab 已同步" : "crontab 不一致";
  sync.className = `pill ${state.cron_in_sync ? "passed" : "warning"}`;
  renderMetrics(jobs);
  renderTable(jobs);
  renderDetail(jobs.find((job) => job.job === selectedJob));
}

document.querySelector("#refresh").addEventListener("click", loadStatus);
loadStatus();
setInterval(loadStatus, 15000);
