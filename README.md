<!-- mcp-name: io.github.CSOAI-ORG/meok-transport-canada-hos-mcp -->
[![MCP Scorecard: 84/100](https://img.shields.io/badge/proofof.ai-84%2F100-5b21b6)](https://proofof.ai/scorecard/meok-transport-canada-hos-mcp.html)

# meok-transport-canada-hos-mcp

> Canadian Hours of Service (SOR/2005-313) + NSC Standard 9/14 carrier safety + ELD T-T-019 + Provincial Ministry of Transport audit prep. Callable compliance toolkit for South-of-60 / North-of-60 / cycle-switch / cross-border CA-US operations. By **MEOK AI Labs**.

## Why this exists

Canadian commercial trucking lives under a federal-provincial split: Transport Canada writes the rules (SOR/2005-313 + NSC Standards), the provinces enforce. A single out-of-service order at an Ontario MTO or Quebec SAAQ scale is enough to:
- Drop a CVOR score (Ontario) or PEVL rating (Quebec) into intervention
- Suspend operating privileges
- Lock cross-border shipping (CBSA + FMCSA cross-reference)
- Spike insurance 25-200% on next renewal
- Force facility audit + remediation pack

This MCP gives Safety Officers, dispatch supervisors, and owner-operators the callable toolkit to **prevent** carrier-rating failure across the full Canadian regulatory stack.

This pairs with [`meok-fmcsa-hours-of-service-mcp`](https://pypi.org/project/meok-fmcsa-hours-of-service-mcp/) — many North American fleets run cross-border CA↔US and need both jurisdictions in one stack.

## Install

```bash
pip install meok-transport-canada-hos-mcp
```

## Claude Desktop config

```json
{
  "mcpServers": {
    "canada-hos": {
      "command": "meok-transport-canada-hos-mcp"
    }
  }
}
```

## Tools (7)

| Tool | Use case |
|------|----------|
| `check_canada_hos_south_60th` | SOR/2005-313 South: 13/14/16/10/70-120 audit |
| `check_canada_hos_north_60th` | SOR/2005-313 North: 15/18/80 (Arctic regime) |
| `check_eld_canada_mandate` | Transport Canada T-T-019: third-party certified only |
| `check_cycle_switch` | Cycle 1 ↔ Cycle 2: 36h off-duty + notification |
| `check_nsc_carrier_safety` | NSC Standard 14 rating: Excellent / Satisfactory / Conditional / Unsatisfactory |
| `audit_cross_border_us_canada` | Which HoS regime applies in which jurisdiction |
| `prepare_carrier_audit_pack` | Provincial MoT audit prep (ON / QC / BC / AB differ) |

## Pricing

- **Free** — MIT self-host
- **Starter** — CAD 49/mo
- **Pro** — CAD 149/mo (multi-driver, multi-province)
- **Fleet** — CAD 999/mo (50+ trucks, cross-border bundle with FMCSA MCP)

[Subscribe Pro → CAD 149/mo](https://www.csoai.org/checkout)

## Regulatory basis

- **SOR/2005-313** — Commercial Vehicle Drivers Hours of Service Regulations
- **NSC Standard 9** — Hours of Service (CCMTA)
- **NSC Standard 10** — Cargo Securement
- **NSC Standard 11** — Periodic Mandatory Vehicle Inspection
- **NSC Standard 13** — Daily Inspection
- **NSC Standard 14** — Carrier Safety Rating
- **Transport Canada T-T-019** — ELD Technical Standard (1 Jan 2023 mandate)
- **CSA Border Carrier Initiative** — CA↔US harmonisation (CBSA / CBP)
- Provincial enforcement:
  - Ontario MTO — CVOR (Commercial Vehicle Operator's Registration)
  - Quebec SAAQ — PEVL (Politique d'évaluation des propriétaires et exploitants de véhicules lourds)
  - BC CVSE — National Safety Code Number
  - Alberta Transportation Carrier Services — Safety Fitness Certificate (SFC)

## Why Canada is stricter than the US on ELDs

The single biggest gotcha for US carriers crossing into Canada: **Canada only accepts THIRD-PARTY CERTIFIED ELDs under T-T-019**. The US allows self-certification — Canada does not. A US-only self-certified ELD is **not** valid for Canadian extra-provincial operation. Use `check_eld_canada_mandate` to verify before any cross-border run.

## Sign your responses

```bash
export MEOK_HMAC_SECRET="your-secret"
meok-transport-canada-hos-mcp
```

## License

MIT © 2026 Nicholas Templeman / MEOK AI Labs · [haulage.app](https://haulage.app)


<!-- GEO-FOOTER:v1 -->

---

### Part of the MEOK constellation

This MCP is one node in a connected ecosystem built by **MEOK AI LABS** around a single
sovereign AI core — governed agents with a hash-chained audit trail, mapped to the CSOAI
compliance charter.

- 🌐 The whole map: **<https://meok.ai/constellation>**
- 🛡️ AI governance & certification: **<https://councilof.ai>** · **<https://csoai.org>**
- ✅ Verify any signed report: **<https://meok.ai/verify>**
