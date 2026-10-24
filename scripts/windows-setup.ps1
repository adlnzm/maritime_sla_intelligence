$ErrorActionPreference = 'Stop'
# Python 3.11 reads .pth with the Windows locale even in UTF-8 mode.
# Install the project as a regular wheel to support non-ASCII repository paths.
$env:UV_LINK_MODE = 'copy'
uv sync --frozen --no-editable --extra dev --extra fabric --extra azure
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& .venv/Scripts/python.exe -X utf8 -c "import maritime; print('Installed maritime', maritime.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'Package import failed' }
