param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsForBuild
)

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "python not found in PATH"
    exit 1
}

python "$PSScriptRoot/build.py" @ArgsForBuild
exit $LASTEXITCODE
