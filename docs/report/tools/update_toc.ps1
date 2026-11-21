# Opens the Word report, fills in its table of contents and page numbers, and saves it. Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File docs\report\tools\update_toc.ps1
# (The PDF does not need this; build_report.py --pdf makes it without Word.)
$ErrorActionPreference = "Stop"
$docx = Join-Path (Get-Location).Path "docs\report\I-ITSM_Project_Report.docx"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($docx)
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    foreach ($toc in $doc.TablesOfContents) { $toc.UpdatePageNumbers() }
    Write-Host ("table of contents updated, pages: " + $doc.ComputeStatistics(2))
    $doc.Save()
    $doc.Close($false)
}
finally {
    $word.Quit()
}
