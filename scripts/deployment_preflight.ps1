param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Output) { throw 'Evidence output already exists; choose a fresh file.' }
$required = @('AZURE_TENANT_ID','AZURE_SUBSCRIPTION_ID','AZURE_RESOURCE_GROUP',
    'AZURE_ML_WORKSPACE','AZURE_API_AUDIENCE','AZURE_OPENAI_ENDPOINT',
    'AZURE_OPENAI_DEPLOYMENT','FABRIC_WORKSPACE_ID','FABRIC_LAKEHOUSE_ID')
$checks = @{}
foreach ($name in $required) { $checks[$name] = [bool][Environment]::GetEnvironmentVariable($name) }
$checks['azure_cli'] = [bool](Get-Command az -ErrorAction SilentlyContinue)
if ($checks['azure_cli']) {
    $account = az account show --output json 2>$null
    $checks['azure_login'] = ($LASTEXITCODE -eq 0)
    if ($checks['azure_login']) {
        $identity = $account | ConvertFrom-Json
        $checks['tenant_matches'] = ($identity.tenantId -eq $env:AZURE_TENANT_ID)
        $checks['subscription_matches'] = ($identity.id -eq $env:AZURE_SUBSCRIPTION_ID)
        az group show --name $env:AZURE_RESOURCE_GROUP --query id --output none 2>$null
        $checks['resource_group_readable'] = ($LASTEXITCODE -eq 0)
    }
}
$passed = @($checks.Values | Where-Object { -not $_ }).Count -eq 0
@{ checked_at = [DateTime]::UtcNow.ToString('o'); checks = $checks;
   status = $(if ($passed) {'PASS_CONFIGURATION_ONLY'} else {'BLOCKED_DEPLOYMENT_ACTION_REQUIRED'});
   permissions = 'Effective data permissions require target execution; configuration is not authorization.'
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding utf8
if (-not $passed) { exit 1 }
