# Get script arguments
param (
    [string]$extensions = "py,gml"
)

$extensionsArray = $extensions -split ','

# Get a list of all tracked files
$trackedFiles = git ls-files | Where-Object { $_ -match "\.($($extensionsArray -join "|"))$" }

# Generate a summary of these files' contents
$summary = ""

foreach ($file in $trackedFiles) {
    $contents = Get-Content $file

    # Skip emtpy files
    if ($contents.Length -eq 0) {
        continue
    }

    $ext = [System.IO.Path]::GetExtension($file)
    $type = ""
    if ($ext -eq ".gml") {
        $type = "gml"
    } elseif ($ext -eq ".py") {
        $type = "python"
    }
    
    $summary += "# ``$($file)```n"
    $summary += "``````$($type)`n"
    $summary += $contents | Out-String
    $summary += "```````n`n"
}

$outFile = "summary.md"
$summary | Out-File $outFile