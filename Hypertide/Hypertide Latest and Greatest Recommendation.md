**The Hypertide Playbook and Help Guide**

**Updated Aug 30, 2025**  
   
**Change Log:**

* Aug 30 \- Turn on “Domain Level Rate Limiting” Within Smartlead  
* June 29 \- Added bulletin with Smartlead Warmup   
* June 26 \- Added Bison Warmup Protocol

### **Inbox and Campaign Settings:**

#### Warmup:

* Warm up is super simple, there’s only one key difference between warm up on smartlead and other tools (the reply rate). 

**Smartlead** (use [smartlead.hypertide.io](http://smartlead.hypertide.io) for bulk updates)**:**

* Entra Inboxes  
  * 5 emails per day  
  * 60% reply rate for SL   
  * 1 email ramp up per day   
  * 14 days of warmup   
  * Reply to inbound Warmup Emails: 8   
  * Do NOT turn on auto adjust warmup/outbound settings  
  * All other settings don’t really matter  
  * For campaigns you want to turn on “Domain-Level Rate Limiting”

* Google Inboxes:  
  * 10 emails per day  
  * 30% reply rate  
  * 1 email ramp up  
  * 14 days of warmup   
  * Reply to Inbound Warmup Emails: Doesn’t matter  
  * Do NOT turn on auto adjust warmup/outbound settings  
  * All other settings don’t really matter

**Instantly (**use [instantly.hypertide.io](http://instantly.hypertide.io) for bulk updates)**:** 

* Entra Inboxes  
  * 5 emails per day  
  * 100% reply rate for Instantly   
  * 1 email ramp up per day   
  * 14 days of warmup   
  * All other settings don’t really matter

* Google Inboxes:  
  * 10 emails per day  
  * 30% reply rate  
  * 1 email ramp up  
  * 14 days of warmup   
  * All other settings don’t really matter

**Bison:**

* Entra Inboxes  
  * 5 emails per day  
  * 14 days of warmup   
  * Reply to inbound Warmup Emails: 3

* Google Inboxes:  
  * 10 emails per day  
  * 14 days of warmup  
  * Reply to Inbound Warmup Emails: 6

    

#### 

#### Outbound Settings  	Entra Inboxes:

* After 14 days of warmup, you can send 2 emails per day. You can send more emails per inbox if your campaign is performing well, but our recommendation is 2 emails per day.  
  * Add 60 minute wait time between emails 

#### 	Google Inboxes:

* After 14 days of warmup, you can send 20 emails per day outbound  
* 35 minute wait time between emails

#### Campaign Settings

* Do NOT track opens or links \- Why? Open tracking adds a small image to your emails and this is not great for deliverability. The embedded tracking pixel flags the email as containing an image, which some spam filters view suspiciously, Many ESPs and mail servers recognize common tracking pixel domains and may route such emails to spam folders, The additional HTML code for tracking can trigger spam filters, especially if implemented poorly. Some email authentication protocols (like DMARC) may fail due to the tracking redirects through third-party servers

  * Do NOT use MX/ESP matching \- Why? MX matching and splitting your lead list essentially make your domains REALLY easy to get flagged by ESP providers. Note: This only applies to Hypertide inboxes \- the key difference here is that Hypertide inboxes are all from 1 domain. Normal setups will have 2-3 inboxes per domain, so when you add 50 inboxes to a campaign, there will naturally be a gap between when the same domain ends up emailing users from a certain ESP. 

  * Do NOT split your lead list by inbox provider \- Why? Similar logic to above. Say you split your leadlist and only have leads with Google Workspace. If your campaign only has Hypertide inboxes, Google will notice that a single domain has emailed a bunch of their users in a very short time period (none of the sending tools allow you to control the gap in emails from inboxes within the same DOMAIN) 

  * Safe / Valid emails ONLY. Do not email catchalls or invalids, doing so will increase your bounces and risk burning your domain.

  * No images or links

  * Keep your copy plain text if possible

  * Use **both** Hypertide domains that you get in an order for a campaign\!

  * Turn on Domain-Level Rate limiting in Smartlead  
  


#### Copy best practices

* The shorter the better  
* Spin tax is a must\! Beyond copy fatigue it is very clear that ESPs are tracking the frequency of how often the same message is sent to its users.  
* Try to change your copy every 1.5 \- 2 months

### **Troubleshooting:**

* **Inboxes are requesting for “Code” to re-enable warmup or warmup is not turning on for \<15% of inboxes on a domain:** This is normal and BY DESIGN. Given Hypertide’s infra is primarily meant for Enterprise \- warmup is not a common feature/sending behavior in enterprise and so the Entra tenant throttles **warmup emails only. The sending tools classify these as “bounces” but they are not true bounces**. In general if up to 15% of your inboxes are NOT warming up \- that is totally OK\! The **domain** reputation will out trump the individual inbox reputation based on how Hypertide inboxes are setup. If more than 15% of your inboxes are not warming up then there’s a problem and it’s best to reach out to Hypertide support. If you do feel like you want to enable warmup for all your inboxes even after some of them stop, then the best way to get the code is to login to the inboxes (we want to emphasize again that this not necessary since **domain reputation** \>\> **individual inbox** reputation and as long as 85% of your inboxes are warming you should be ok\!). The inboxes WILL still send and receive **campaign** emails. There is **NO** difference to having these unblocked and will only add operational complexity. 

* **Inboxes get disconnected:** There are two types of disconnects that happen, 1 which requires a full reconnect and one which will work with a bulk reconnect and won’t require a password. The second one is easy to in both instantly and smartlead. If you need to re-connect specific inboxes, please email [support@hypertide.io](mailto:support@hypertide.io)  and we will connect the inboxes within 24 hours

* **Bounce rate \> 5%:** This usually means your copy has been flagged by ESPs. Its hard to estimate how long this may take, but can range anywhere from 1 months to 6 months for this to start occurring. To solve this you can change your campaign email copy, or even increase your warmup so there is more variability in your outbound emails. This will also start occurring if you launch before 14 days of warmup. If you notice that ALL your bounces are from 1 domain then you need to alert Support. This usually happens because SL sends a TON of warm up emails all at once and doesn’t follow the guidance provided. This naturally causes the tenant to lock down \- no biggie, the support team can help you move your inboxes to a new and fresh tenant and have you up and running within 24 hours. This is a RARE occurrence but it can happen. Note that if you are getting bounces due to your domain or copy a tenant change **will not** help improve your bounce rates.

* **Not receiving test emails?** Try creating a campaign and adding your test inboxes as leads. Testing emails may use a different protocol to send their test email vs the campaign settings so please test the Entra inboxes in a campaign rather and don’t be concerned if you don’t receive the “test” email.

* **Some inboxes aren’t *sending* warmup emails?** This setup is intentional. In larger enterprises—like the Entra infrastructure that Hypertide operates on—many inboxes primarily receive emails rather than send them, typically with an 80/20 received-to-sent ratio. Once these inboxes are actively used for outbound, you’ll see the sending activity increase. However, if they were sending both outbound and warmup emails, it would distort the metrics. On the backend, we align warmup behavior with how enterprise inboxes naturally function. In terms of deliverability, there’s no impact—*domain health* always takes precedence over *individual inbox health*. As a result, these inboxes will still achieve strong deliverability when sending outbound emails. That said, if you’re seeing this behavior in 80% or more of the inboxes within a domain, it could indicate an issue that should be addressed.

### **A Hypertide Order:**

* Costs $50/mo \+ one time domain fee ($15.5 per domain \- only .com domains) or you can bring your own domains (any tld works)  
  * 2 domains   
  * 50-52 inboxes each domain so 100-104 inboxes total per order  
  * 2 recommended outbound emails per day per inbox. You can ramp these to 3 and 4 if your campaigns are doing well but that may burn domains/inboxes faster  
  * 2 outbound emails per day \* 100 inboxes \= 200 emails per day \= 5k emails per month

### **Domain Recommendations:**

* Use aged domains. Domains registered within what it seems like a 2-4 week period are penalized more heavily.   
* We’ve seen good results with .com and .co \- If you want to play it safe just use .com

### **Tools to Make your Life Easier:**

* Bulk Smartlead Inbox Settings: [smartlead.hypertide.io](http://smartlead.hypertide.io)  
* Bulk Instantly Inbox Settings: instantly.hypertide.io

### **Changing your forwarding domain & Changing Inbox Names:**

* If you’d like to change the URL where your Hypertide domains are forwarding, please just send an email to [support@hypertide.io](mailto:support@hypertide.io) and we can update that for you.  
* Similarly, if you want to change names for any of your inboxes, please just email support@hypertide.io and we’ll update the names for you. **You must delete the old inboxes because they will start disconnecting otherwise and you’ll get a ton of notifications.**

### **Custom Tracking Domains:**

Custom tracking DNS should be added by default \- however, sometimes the automation misses adding this record. The Hypertide team does NOT recommend using custom tracking as we have seen it drop deliverability.

* Instantly: “inst”  
* Smartlead: “smart”

### **Canceling an Order:**

* Canceling an order is super simple, you can do it directly within the Hypertide app. Click your initials in the top right corner, then click on “billing”. That will take you to a stripe page where you can view all your subscriptions with Hypertide. Click “View More” if you have a ton of subscriptions. Once here, **right click the cancel subscription button for each subscription you’d like to cancel and click on “open in new tab”**. This way you can cancel multiple subscriptions at once \- otherwise you will have to go through the whole process again.

* Swapping Burned Domains: If you would swap burned domains, please send an email to [support@hypertide.io](mailto:support@hypertide.io) with which domain you would like swap. Please note at this time you will have to provide domains for us to swap.