// Power Query function for local JSON marts. Pass a single successful run folder.
(RunFolder as text, TableName as text) as table =>
let
    Rows = Json.Document(File.Contents(RunFolder & "/" & TableName & ".json")),
    Result = Table.FromRecords(Rows)
in
    Result
