-- Fabric Lakehouse SQL endpoint. Only successful, read-back-verified runs are exposed.
-- Run after Fabric acceptance creates maritime_published_runs.
CREATE OR ALTER VIEW dbo.control_tower AS
WITH latest AS (
    SELECT TOP (1) run_id FROM dbo.maritime_published_runs
    WHERE status = 'SUCCESS' ORDER BY published_at DESC
)
SELECT p.port_id, p.name, p.country, p.latitude, p.longitude,
       c.date, c.category, c.stress_score, c.deviation_fraction,
       c.persistence_days, c.classification, c.lineage_id, c.run_id
FROM dbo.dim_ports p
JOIN dbo.fact_congestion c ON c.port_id=p.port_id AND c.run_id=p.run_id
JOIN latest r ON r.run_id=c.run_id;
GO
CREATE OR ALTER VIEW dbo.sla_control AS
SELECT s.shipment_id, s.origin, s.destination, s.promised_delivery,
       r.expected_delay_hours, r.breach_probability, r.expected_loss,
       d.recommended_action, d.expected_benefit,
       r.classification, r.lineage_id, r.run_id
FROM dbo.dim_scenarios s
JOIN dbo.fact_sla_risk r ON r.shipment_id=s.shipment_id AND r.run_id=s.run_id
JOIN dbo.fact_decisions d ON d.shipment_id=s.shipment_id AND d.run_id=s.run_id;
