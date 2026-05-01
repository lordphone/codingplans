-- Replace string `quantization` label with boolean `aggressively_quantized`.
-- NULL = untested; true = aggressively quantized (sub-8-bit); false = standard (>=8-bit).
-- Existing data is seed/fake — drop the column outright.

alter table public.benchmark_runs drop column if exists quantization;
alter table public.benchmark_runs add column aggressively_quantized boolean null;
