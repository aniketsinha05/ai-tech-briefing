const dateSelect = document.querySelector("#date-select");
const searchInput = document.querySelector("#search");
const briefingRoot = document.querySelector("#briefing");
const statusNode = document.querySelector("#status");
const emptyNode = document.querySelector("#empty");
const countNode = document.querySelector("#count");
let briefings = [];
let activeDate = "";

const sectionDescriptions = {
  india: "AI, policy, startups and technology across India.",
  global: "Major international launches, research, companies and policy."
};
const keyOf = item => String(item.section || "briefing").toLowerCase();

const escapeHtml = (value = "") => String(value).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const formatDate = value => {
  const parsed = new Date(value + "T12:00:00Z");
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat("en-IN", {day:"numeric",month:"long",year:"numeric",timeZone:"UTC"}).format(parsed);
};
const hostInitials = host => (host || "web").replace(/^www\./,"").split(".")[0].slice(0,2).toUpperCase();
function sourceCard(source) {
  const url = escapeHtml(source.url);
  const title = escapeHtml(source.title || source.domain || source.url);
  const domain = escapeHtml(source.domain || source.url);
  const description = source.description ? `<span class="source-description">${escapeHtml(source.description)}</span>` : "";
  return `<a class="source-card" href="${url}" target="_blank" rel="noopener noreferrer"><span class="source-icon">${escapeHtml(hostInitials(source.domain))}</span><span class="source-copy"><span class="source-domain">${domain}</span><span class="source-title">${title}</span>${description}<span class="source-action">Read original source ↗</span></span></a>`;
}
function splitSentences(text) {
  return (text || "").split(/(?<=[.!?])\s+(?=[A-Z“"₹$€])/).map(s => s.trim()).filter(Boolean);
}
function storyBody(summary) {
  const s = splitSentences(summary);
  if (!s.length) return `<p class="lead">Open a source below for more details.</p>`;
  const takeaway = s.length >= 3 ? s[s.length - 1] : "";
  const middle = s.slice(1, takeaway ? -1 : undefined).join(" ");
  return `<p class="lead">${escapeHtml(s[0])}</p>${middle ? `<p class="detail">${escapeHtml(middle)}</p>` : ""}${takeaway ? `<div class="takeaway"><span>Why it matters</span>${escapeHtml(takeaway)}</div>` : ""}`;
}
function watchText(text) {
  const m = text.match(/^([^:]{3,45}):\s+(.*)$/);
  return m ? `<strong class="watch-label">${escapeHtml(m[1])}</strong><span>${escapeHtml(m[2])}</span>` : `<span>${escapeHtml(text)}</span>`;
}
function render() {
  const query = searchInput.value.trim().toLowerCase();
  const chosen = briefings.find(item => item.date === activeDate);
  if (!chosen) {
    briefingRoot.innerHTML = "";
    emptyNode.hidden = false;
    statusNode.textContent = "No briefing has been published for this date yet.";
    return;
  }
  const stories = chosen.items.filter(item => [item.title,item.summary,item.section_title,...item.sources.map(s => [s.title,s.domain,s.description].join(" "))].join(" ").toLowerCase().includes(query));
  countNode.textContent = `${briefings.length} ${briefings.length === 1 ? "day" : "days"} archived`;
  statusNode.textContent = query ? `${stories.length} matching ${stories.length === 1 ? "story" : "stories"} for ${formatDate(chosen.date)}` : `${chosen.items.length} stories · Updated ${chosen.prepared || "daily"}`;
  emptyNode.hidden = stories.length > 0 || !query;
  const note = chosen.note ? `<div class="briefing-note"><strong>Editor's note</strong><span>${escapeHtml(chosen.note)}</span></div>` : "";

  // Sections come from the file itself, in the order they appear.
  const sections = [];
  chosen.items.forEach(item => {
    const key = keyOf(item);
    if (!sections.some(s => s.key === key)) {
      sections.push({ key, title: item.section_title || "More developments", description: sectionDescriptions[key] || "" });
    }
  });

  const sectionMarkup = sections.map(section => {
    const sectionStories = stories.filter(item => keyOf(item) === section.key);
    if (!sectionStories.length) return "";
    const cards = sectionStories.map(item => `<article class="story">
      <div class="story-top"><span class="story-number">${String(item.number).padStart(2,"0")}</span>
        <div class="story-body"><h4>${escapeHtml(item.title)}</h4>${storyBody(item.summary)}</div>
      </div>
      ${item.sources.length ? `<div class="source-grid">${item.sources.map(sourceCard).join("")}</div>` : ""}
    </article>`).join("");
    return `<section class="news-section" id="sec-${escapeHtml(section.key)}"><div class="news-section-head"><div><h4>${escapeHtml(section.title)}</h4>${section.description ? `<p>${escapeHtml(section.description)}</p>` : ""}</div><span class="section-count">${sectionStories.length} stories</span></div><div class="story-list">${cards}</div></section>`;
  }).join("");

  const watch = chosen.what_to_watch?.length ? `<aside class="watch-panel" id="sec-watch"><h4><span aria-hidden="true">◈</span> What to watch next</h4><ul>${chosen.what_to_watch.map(item => {
    const text = typeof item === "string" ? item : item.text;
    const sources = typeof item === "string" ? [] : (item.sources || []);
    return `<li>${watchText(text)}${sources.length ? `<div class="watch-sources">${sources.map(sourceCard).join("")}</div>` : ""}</li>`;
  }).join("")}</ul></aside>` : "";

  const navItems = sections
    .map(s => ({ id: "sec-" + s.key, label: s.title, n: stories.filter(i => keyOf(i) === s.key).length }))
    .filter(x => x.n);
  if (watch) navItems.push({ id: "sec-watch", label: "What to watch", n: chosen.what_to_watch.length });
  const nav = navItems.length > 1 ? `<nav class="section-nav" aria-label="Jump to section">${navItems.map(x => `<a href="#${escapeHtml(x.id)}">${escapeHtml(x.label)}<b>${x.n}</b></a>`).join("")}</nav>` : "";

  const verification = chosen.verification_note ? `<aside class="verification-panel"><h4>Sources & verification note</h4><p>${escapeHtml(chosen.verification_note)}</p></aside>` : "";
  briefingRoot.innerHTML = `<div class="briefing-header"><div><div class="briefing-date">COVERAGE DATE · IST</div><h3>${escapeHtml(chosen.coverage || formatDate(chosen.date))}</h3><div class="prepared">${chosen.prepared ? "Prepared " + escapeHtml(chosen.prepared) : "Daily AI & technology digest"}</div></div></div>${note}${nav}${sectionMarkup}${watch}${verification}`;
}
async function init() {
  try {
    const response = await fetch("briefings.json", {cache:"no-store"});
    if (!response.ok) throw new Error("Archive data could not be loaded.");
    briefings = await response.json();
    briefings.sort((a,b) => b.date.localeCompare(a.date));
    dateSelect.innerHTML = briefings.map(item => `<option value="${escapeHtml(item.date)}">${escapeHtml(formatDate(item.date))}</option>`).join("");
    activeDate = briefings[0]?.date || "";
    if (!briefings.length) {
      dateSelect.innerHTML = '<option value="">No dates available</option>';
      statusNode.textContent = "No dated .txt briefings found yet. The archive will appear here after the first file is pushed.";
      countNode.textContent = "0 days archived";
      emptyNode.hidden = false;
      return;
    }
    dateSelect.value = activeDate;
    render();
  } catch (error) {
    statusNode.textContent = error.message + " Please check the GitHub Pages deployment.";
    countNode.textContent = "Unavailable";
  }
}
dateSelect.addEventListener("change", () => { activeDate = dateSelect.value; render(); });
searchInput.addEventListener("input", render);
init();