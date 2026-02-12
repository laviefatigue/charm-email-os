--
-- Charm Email OS - Seed Data for Local Development
-- Synced from production with sensitive data removed
--

SET statement_timeout = 0;
SET lock_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: emailbison_instances; Type: TABLE DATA; Schema: public; Owner: -
-- MUST be loaded first (workspaces references this)
--

COPY public.emailbison_instances (id, instance_name, api_url, api_key_encrypted, is_active, last_sync_at, created_at, updated_at, notes) FROM stdin;
4051d513-99ad-45bd-ad6c-b4366b9e0944	EmailBison Production	https://spellcast.hirecharm.com	\N	t	2026-02-10 12:00:00+00	2025-10-31 00:00:00+00	2026-02-10 12:00:00+00	Primary EmailBison instance
\.


--
-- Data for Name: workspaces; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.workspaces (id, instance_id, workspace_name, emailbison_workspace_id, is_active, last_sync_at, created_at, updated_at, sender_account_count, domain_count, notes, automation_enabled) FROM stdin;
b9abd34a-f16a-4b92-bda0-5af10f8c44bd	4051d513-99ad-45bd-ad6c-b4366b9e0944	Charm	2	t	2026-02-10 12:00:13.953245+00	2025-10-31 03:30:08.854285+00	2026-02-10 16:35:53.264609+00	187	77	\N	t
1e57b7dd-4678-4c97-916b-8b79b748d735	4051d513-99ad-45bd-ad6c-b4366b9e0944	Stable Kernel	6	t	2026-02-10 12:00:13.953245+00	2025-10-31 03:30:08.854285+00	2026-02-10 12:08:42.959269+00	163	6	\N	t
3fabfb3c-80d1-4991-8834-70cfbe0c97b9	4051d513-99ad-45bd-ad6c-b4366b9e0944	Selery	22	t	2026-02-10 12:00:13.953245+00	2026-01-21 20:24:55.697233+00	2026-02-10 12:08:17.018498+00	692	45	\N	t
\.


--
-- Data for Name: clients; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.clients (id, name, context, created_at, updated_at, workspace_id, logo_url, onboarding_complete, onboarding_data, contact_name, contact_email, website, industry, domain_pattern) FROM stdin;
4bd07dc0-059a-448b-b6f4-3275d0c104a9	Charm	{}	2026-01-14 20:45:39.149363+00	2026-01-31 01:38:09.618515+00	b9abd34a-f16a-4b92-bda0-5af10f8c44bd	\N	t	{"primaryDomain": "hirecharm.com", "baseSenderNames": [{"firstName": "Chris", "lastName": "Booth", "isFounder": true}]}	\N	\N	https://hirecharm.com	\N	\N
e5988a33-ec6c-4b5a-be85-25b8bd0678bb	Selery	{}	2026-01-21 19:20:07.223703+00	2026-01-21 20:24:55.702082+00	3fabfb3c-80d1-4991-8834-70cfbe0c97b9	\N	f	\N	\N	\N	https://www.seleryfulfillment.com/	SaaS	\N
070387df-7354-4698-a122-010eb023cff3	Stable Kernel	{}	2026-01-14 20:45:38.852042+00	2026-01-14 20:45:38.852042+00	1e57b7dd-4678-4c97-916b-8b79b748d735	\N	t	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: strategies; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategies (id, client_id, name, description, status, emailbison_campaign_id, created_at, updated_at, submission_id) FROM stdin;
8e1dc103-2523-4023-a8c5-d78d003f519a	4bd07dc0-059a-448b-b6f4-3275d0c104a9	Default Strategy	\N	active	\N	2026-01-20 05:52:25.190489	2026-01-20 05:52:25.190489	\N
05b4cd3b-3ef9-4ac6-8746-b0a0f7bfc875	e5988a33-ec6c-4b5a-be85-25b8bd0678bb	Default Strategy	\N	active	\N	2026-01-21 20:49:00.181392	2026-01-21 20:49:00.181392	\N
\.


--
-- Data for Name: client_onboarding_submissions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.client_onboarding_submissions (id, client_id, submission_version, company_name, website, contact_name, contact_email, employee_count, funding_stage, hq_location, core_product, target_customer, annual_revenue, acv, sales_cycle_length, self_serve_pct, signals, signal_details, job_titles, outbound_tools, outbound_tools_other, crm, lead_sources, customer_voice, roi_results, case_studies_description, case_studies, tone_style, messaging_notes, primary_gtm_objective, primary_gtm_objective_other, success_metrics, success_definition, timeline_urgency, monthly_budget, submission_status, submitted_at, processed_at, created_at, updated_at, industry, competitors, key_differentiators, common_objections, buying_triggers_global, monthly_volume, current_open_rate, current_reply_rate, other_channels, messages_worked, approaches_failed, industry_jargon, engagement_win, additional_context, core_vendors) FROM stdin;
9c1d635a-f69b-42f5-ba82-72fed49f4476	4bd07dc0-059a-448b-b6f4-3275d0c104a9	1	Charm	https://hirecharm.com	Chris Booth	chris@hirecharm.com	50-200	Seed	Atlanta, GA	Outbound infrastructure that delivers meetings, not just sends emails	Founders and revenue leaders at B2B SaaS companies who are scaling outbound but getting burned by low reply rates	\N	$60-100K/year	2-4 weeks	\N	{"hiring","funding","tools"}	{"hiring": ["Posted SDR job in last 30 days", "New sales hire on LinkedIn"], "funding": ["Recent funding announcement", "Hiring VP of Sales"], "tools": ["Using Instantly or Apollo", "Searching for email warmup solutions"]}	{"VP of Sales","Head of Growth","Revenue Operations","Founder/CEO"}	{Apollo,Instantly,Smartlead}	\N	Salesforce	{ZoomInfo,Apollo,Clearbit}	We were burning through domains every 2 weeks before Charm. Finally someone who understands the infrastructure side.	47 meetings in 60 days for mid-market SaaS. 4-8% reply rate vs industry 1-2%. $180 cost per meeting vs $400+ industry average.	Anonymized case studies available. 47-meetings story is the go-to.	\N	professional	Professional but not corporate. Direct, not salesy. Technical credibility without jargon overload.	Increase qualified meetings	Increase qualified meetings from outbound by 3x while reducing cost per meeting by 50%	{"Meetings booked per month","Reply rate (%)","Cost per meeting ($)"}	A qualified meeting booked with the right ICP. Not just a reply.	immediate	$5K-15K/month	submitted	2026-02-10 04:34:45+00	\N	2026-01-21 19:20:07.223703+00	2026-02-10 04:34:45+00	SaaS	{Apollo,Instantly,Smartlead}	Managed infrastructure vs. DIY tools. We own the boring stuff so sales owns the selling.	We have heard we can do this ourselves a lot. The truth is you can, but you will burn through domains 3x faster.	Internal pressure to hit pipeline targets. Domain issues causing deliverability drops. New funding with aggressive growth goals.	5000	35%	3%	LinkedIn, Events, Warm referrals	Short, punchy emails that reference specific pain points.	Long-form educational content in first touch. Generic feature lists.	Infrastructure, deliverability, warmup, domain health, inbox rotation	A qualified meeting booked with the right ICP.	We are seeing momentum with VP of Sales personas. They feel the pain of deliverability most directly.	{Salesforce,HubSpot,Apollo}
\.


--
-- Data for Name: campaign_cycles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.campaign_cycles (id, client_id, strategy_id, cycle_number, cycle_name, start_date, end_date, duration_days, target_campaigns, actual_campaigns, status, notes, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: strategy_generation_jobs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategy_generation_jobs (id, client_id, submission_id, status, generation_round, error_message, created_at, started_at, completed_at, strategy_id, revision_of, job_type, strategy_considerations) FROM stdin;
\.


--
-- PostgreSQL database dump complete
--
