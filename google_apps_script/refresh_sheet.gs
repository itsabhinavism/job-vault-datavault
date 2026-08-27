// JobVault sheet auto-refresh.
//
// Bound to your JobVault spreadsheet (Extensions -> Apps Script).
// Every day it fetches the CSVs from the GitHub repo and refills
// the matching tabs, so the sheet is always current without re-uploading.
// Because the GitHub CSVs are themselves refreshed daily by the local
// cron batch, the whole chain is automated: local cron -> GitHub -> sheet.

var CONFIG = [
  { tab: "current_jobs", url: "https://raw.githubusercontent.com/itsabhinavism/job-vault-datavault/main/export/current_jobs.csv" },
  { tab: "job_history",  url: "https://raw.githubusercontent.com/itsabhinavism/job-vault-datavault/main/export/job_history.csv" },
  { tab: "jobs_by_day",  url: "https://raw.githubusercontent.com/itsabhinavism/job-vault-datavault/main/export/jobs_by_day.csv" },
  { tab: "changes",      url: "https://raw.githubusercontent.com/itsabhinavism/job-vault-datavault/main/export/changes.csv" },
  { tab: "skills",       url: "https://raw.githubusercontent.com/itsabhinavism/job-vault-datavault/main/export/skills.csv" },
  { tab: "salary_data",  url: "https://raw.githubusercontent.com/itsabhinavism/job-vault-datavault/main/export/salary_data.csv" },
  { tab: "jobs_by_mode", url: "https://raw.githubusercontent.com/itsabhinavism/job-vault-datavault/main/export/jobs_by_mode.csv" }
];

// Refresh every tab now. Run this once to test.
function refreshAll() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  for (var i = 0; i < CONFIG.length; i++) {
    var c = CONFIG[i];
    var sheet = ss.getSheetByName(c.tab);
    if (!sheet) sheet = ss.insertSheet(c.tab);
    var csv = UrlFetchApp.fetch(c.url).getContentText().replace(/^\uFEFF/, "");  // strip BOM
    var values = Utilities.parseCsv(csv);
    sheet.clear();
    if (values.length) sheet.getRange(1, 1, values.length, values[0].length).setValues(values);
  }
}

// Install once, then the refresh runs automatically every day at 21:00 (9 PM).
function installDailyTrigger() {
  ScriptApp.newTrigger("refreshAll")
    .timeBased()
    .everyDays(1)
    .atHour(21)
    .create();
}

// Optional: remove all triggers.
function clearTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
}