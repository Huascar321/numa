# Design

AI settings enable/disable OpenRouter or Groq, retain encrypted server keys,
fetch/configure model lists, and allow manual models. AI may suggest category,
merchant normalization, glosa interpretation, and automation. Local JSON-schema
validation always runs. Groq strict structured outputs and OpenRouter compatible
parameters/provider.require_parameters are used where supported. Models such as
GPT-OSS 20B/120B are changeable recommendations, not hardcoding.
For BCP QR, AI may suggest a category from a non-default informative glosa only;
it cannot fill missing glosa, alter raw glosa, or create a transfer subtype as
an authoritative financial fact.
