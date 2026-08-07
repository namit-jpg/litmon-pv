Partner Feedback – Expanded Product Requirements
1. Consolidated Requirement
The Pharma Literature Monitoring App should automate the monitoring of medical literature for selected pharmaceutical products and their active ingredients.
The application should search approved literature sources, identify potentially relevant safety information, extract important details, classify the result, generate a detection report and alert the responsible pharmacovigilance user.
The user should then be able to review the identified report and decide whether it should:
Be considered a potential safety signal.
Be retained for further assessment.
Be rejected as irrelevant or invalid.
Be prepared for regulatory submission.
Be stored internally without submission.
The objective is to minimise manual literature screening while keeping a qualified pharmacovigilance professional responsible for the final decision.

2. Proposed End-to-End Workflow
Step 1: Product Configuration
The client should be able to configure the products that need to be monitored.
For the initial pilot, the application should support:
Four pharmaceutical products.
Product brand name.
Generic name.
Active ingredient.
Active Pharmaceutical Ingredient, or API.
Relevant synonyms and alternative molecule names.
Manufacturer or marketing authorisation holder.
Markets or countries in which the product is sold.
Literature-monitoring frequency.
Each product should be linked to the user responsible for reviewing alerts and reports.
Step 2: Literature Source Configuration
The initial application should monitor publicly available biomedical literature sources, including:
PubMed.
National Library of Medicine, or NLM, resources.
National Center for Biotechnology Information, or NCBI, resources.
Other approved open-access medical literature sources.
The application should allow additional literature sources to be added later.
The distinction between PubMed, NLM and NCBI must be handled correctly in the product design. PubMed is the literature-search platform, while NLM and NCBI provide the broader infrastructure and databases supporting these services.
Step 3: Automated Literature Search
The application should run searches automatically based on the configured schedule.
Search criteria should consider:
Product name.
Generic name.
Active ingredient.
API.
Known synonyms.
Adverse-event terminology.
Safety-related keywords.
Drug-interaction terms.
Special-situation terms.
Product-quality concerns.
Relevant patient or treatment context.
Users should not be required to run each search manually.
Step 4: Article Validation and Screening
The system should review the search results and classify each result.
Suggested classifications include:
Potentially relevant.
Potential safety signal.
Adverse-event-related.
Product-quality-related.
Duplicate.
Irrelevant.
Invalid.
Insufficient information.
Requires human review.
The partner mentioned that an “invalid” result should generate an alert. The exact meaning of invalid must be confirmed. It could refer to:
An invalid product or ingredient configuration.
An unsuccessful literature search.
An inaccessible article.
A report with missing information.
An article that cannot be processed.
A potentially invalid safety case.
Until clarified, the system should maintain a general exception category and alert the assigned user whenever processing cannot be completed successfully.
Step 5: Information Extraction
For relevant articles, the system should extract structured information, including:
Article title.
Author names.
Journal name.
Publication date.
PubMed ID or other source identifier.
Product or drug mentioned.
Active ingredient.
Suspected adverse event.
Patient information, where available.
Treatment indication.
Dosage information, where available.
Seriousness indicators.
Outcome.
Country of occurrence.
Reporter or source type.
Relevant article excerpts.
Reason the article was classified as relevant.
Confidence or relevance score.
Date and time the article was processed.
The extracted information should be presented in a consistent report format.
Step 6: Signal Tagging
The application should allow reports to be tagged as a potential signal.
Suggested tags include:
Potential signal.
Confirmed signal.
Under review.
Adverse event.
Serious adverse event.
Product quality issue.
Lack of efficacy.
Drug interaction.
Special situation.
Duplicate.
Invalid.
Not relevant.
Submission required.
Submission not required.
AI may recommend the initial tag, but the pharmacovigilance user must be able to change or confirm it.
A report should not automatically become a confirmed signal without human assessment.
Step 7: Automated Alert System
A primary user should be assigned to each client, product or product group.
The assigned user should receive an alert when:
A potential safety signal is detected.
A serious or high-priority result is identified.
An invalid or failed processing event occurs.
A report is awaiting review.
A regulatory reporting deadline is approaching.
A report remains unresolved beyond the defined review period.
A scheduled literature search fails.
No literature search has been completed within the expected monitoring period.
Step 8: Omnichannel Notifications
The partner requested omnichannel alerting.
The initial application can support:
In-application notifications.
Email alerts.
Future channels may include:
SMS.
Microsoft Teams.
Slack.
WhatsApp.
Mobile push notifications.
The channels required for the pilot should be confirmed before development. Email and in-application alerts are recommended for the initial release because they are simpler to implement, test and audit.
Step 9: User Folder and Work Queue
Each user should have a dedicated workspace or folder.
The workspace should contain:
New alerts.
Reports awaiting review.
Potential signals.
Invalid or failed results.
Reports under assessment.
Reports approved for submission.
Reports not selected for submission.
Submitted reports.
Archived reports.
Users should be able to filter reports by:
Product.
Ingredient or API.
Date.
Literature source.
Classification.
Signal status.
Submission status.
Assigned user.
Priority.
Review status.
This will replace the need to manually maintain separate files, spreadsheets and email folders.
Step 10: Review and Decision Workflow
The assigned user should be able to open the extracted report and record a decision.
Suggested decisions include:
Accept as potentially relevant.
Mark as a potential signal.
Request additional assessment.
Mark as invalid.
Mark as duplicate.
Mark as not relevant.
Prepare for regulatory submission.
Retain internally without submission.
Close the report.
The system should capture:
Reviewer name.
Review date and time.
Decision.
Comments.
Supporting documents.
Previous and revised classifications.
Submission decision.
Reason for submission or non-submission.
Step 11: Detection Report
The application should generate a standard literature-detection report for each potentially relevant article.
The report should contain:
Product and ingredient details.
Search source and search date.
Search terms used.
Article details.
Extracted safety information.
Proposed classification.
Potential signal tag.
AI-generated summary.
Human reviewer decision.
Submission status.
Audit history.
For the pilot, mock detection reports should be created using representative literature examples.
These reports will help demonstrate how the system reduces manual effort and standardises the review process.
Step 12: User Dashboard
The dashboard should provide a clear operational view for the pharmacovigilance user.
Recommended dashboard measures include:
Total articles identified.
Articles screened.
Relevant articles.
Irrelevant articles.
Potential signals.
Invalid or failed records.
Reports awaiting review.
Reports approved for submission.
Reports retained without submission.
Reports submitted.
Overdue reviews.
Alerts by priority.
Results by product.
Results by ingredient or API.
Results by literature source.
Search completion status.
The dashboard should allow users to move directly from a metric to the underlying reports.
Step 13: Indian Regulatory Reporting
The partner requested reporting aligned with Indian regulatory requirements, including an XML output.
The application should therefore support:
Extraction of the regulatory information required for the Indian reporting process.
Mapping of extracted literature information into a structured regulatory report.
Generation of a human-readable report.
Generation of an XML file after the required structure has been validated.
Validation of mandatory information before the report is prepared.
Identification of missing regulatory information.
Storage of all generated versions.
Recording whether the report was submitted.
The precise CDSCO XML structure, mandatory fields, validation rules and submission process have not yet been provided in the meeting notes. These must be confirmed with the pharmacovigilance partner before development.
The product should not claim to provide a CDSCO-compliant XML submission until the official format and acceptance requirements have been validated.
Step 14: Submission or Storage Decision
The application should not automatically submit reports to a regulatory authority.
Instead, the user should be able to:
Review the report.
Confirm whether it should be submitted.
Generate the required report or XML file.
Download the submission file.
Upload it to the applicable regulatory gateway.
Record the submission reference.
Retain the report without submitting it.
Store the report for audit and future review.
This keeps the final regulatory decision with the authorised pharmacovigilance user.
Step 15: Regulatory Gateway
The note refers to allowing users to “put it into the gateway.”
For the initial version, the recommended approach is:
The application generates the required report or XML file.
The user downloads the file.
The user manually uploads it to the applicable regulatory gateway.
The user records the submission reference and date in the application.
A direct gateway integration can be considered in a later phase after confirming:
The exact regulatory portal.
Whether integration APIs are available.
Authentication requirements.
File-validation requirements.
Submission acknowledgements.
Error-handling requirements.

3. Dual Operating Model
The partner has proposed two ways of positioning and operating the product.
Model 1: Internal Company Use
A pharmaceutical company purchases the application and uses it through its own pharmacovigilance team.
The company is responsible for:
Product setup.
Reviewing alerts.
Assessing potential signals.
Making submission decisions.
Uploading regulatory reports.
Maintaining internal oversight.
Model 2: Third-Party Pharmacovigilance Service
The application can also be used by the partner as a third-party pharmacovigilance service provider.
Under this model:
The partner monitors literature on behalf of pharmaceutical manufacturers.
The partner reviews system-generated alerts.
The partner prepares detection reports.
The partner sends reports to the manufacturer for approval.
The manufacturer decides whether the case should be submitted.
The partner may assist with preparing regulatory files and documentation.
This creates two potential revenue streams:
Software subscription revenue.
Managed pharmacovigilance service revenue.
The product architecture should therefore eventually support multiple client companies, separate product portfolios, segregated data and role-based access.

4. Trial and Pilot Approach
The partner wants prospective clients to experience the system before making a long-term commitment.
A controlled trial should be designed around:
One pilot pharmaceutical company.
Four products.
Product names, ingredients and APIs configured.
PubMed-based literature monitoring.
A defined historical literature period.
Automated extraction.
Potential signal tagging.
Single-user alerts.
A user folder or work queue.
A dashboard.
Mock detection reports.
A regulatory report prototype.
Manual decision to submit or store.
The trial should demonstrate the overall impact of the product rather than every future feature.
The main pilot message should be:
The application continuously monitors literature, identifies possible safety information, alerts the responsible user, prepares the report and keeps a complete record—while the pharmacovigilance professional remains in control of the final decision.

5. Pilot Success Measures
The pilot should measure whether the application can:
Find literature related to the selected products and ingredients.
Reduce the number of articles requiring manual review.
Correctly identify potentially relevant articles.
Generate understandable summaries.
Extract the required safety information.
Alert the assigned user promptly.
Maintain a usable review folder.
Generate consistent detection reports.
Record the user’s final decision.
Produce a regulatory-reporting output prototype.
Maintain an audit trail.
Reduce the overall time required for literature monitoring.
A comparison should be performed between:
The current manual process.
The application-assisted process.

6. Recommended MVP Scope
The initial MVP should include the following capabilities:
Configuration of four products.
Configuration of ingredients, APIs and synonyms.
PubMed literature search.
Scheduled automated searches.
Article retrieval and deduplication.
AI-assisted relevance screening.
Structured information extraction.
Potential signal tagging.
Invalid-processing alerts.
Single-user assignment.
Email and in-application alerts.
User work folder.
Basic dashboard.
Mock detection report.
Human review and decision workflow.
Store, reject or prepare-for-submission options.
Downloadable regulatory report.
Prototype XML export, subject to regulatory-format validation.
Complete audit trail.

7. Capabilities Recommended for a Later Phase
The following should not be prioritised for the first pilot unless specifically required:
SMS alerts.
WhatsApp alerts.
Microsoft Teams or Slack alerts.
Mobile application.
Multi-level escalation workflows.
Automatic regulatory submission.
Direct CDSCO gateway integration.
Paid literature-source integrations.
Full-text access to subscription journals.
Advanced signal detection across multiple products.
Trend analysis across historical cases.
Multi-country regulatory-reporting formats.
Automated case creation in third-party safety systems.
Advanced multilingual processing.
Customer-facing managed-service portal.
Billing and subscription management.

8. Important Open Clarifications
The following terms and requirements from the meeting notes need confirmation before they are added to the final PRD.
“PVH”
The term “PVH” is not sufficiently clear from the notes.
It may refer to:
Pharmacovigilance Head.
Pharmacovigilance Hub.
A pharmacovigilance platform.
A regulatory programme.
A specific organisation or system.
The partner should provide the full form and intended use.
“Invalid”
The exact event that should be considered invalid must be defined.
Possible interpretations include:
Invalid article.
Invalid source.
Invalid product configuration.
Invalid ingredient or API.
Failed article extraction.
Incomplete safety report.
Non-reportable case.
“Sub-standard subpoenas”
This phrase appears to be a transcription or note-taking error and should not be interpreted without confirmation.
The intended term may relate to:
Substandard medicines.
Suspected quality defects.
Substandard substances.
Spontaneous reports.
Product-quality complaints.
The partner should confirm the exact phrase and expected functionality.
“Gateway”
The applicable gateway must be identified.
It could refer to:
A CDSCO submission portal.
A PvPI reporting system.
The pharmaceutical company’s internal safety system.
A third-party pharmacovigilance platform.
Another regulatory reporting portal.
XML Format
The partner must provide or validate:
The required XML schema.
Mandatory fields.
Validation rules.
Example accepted files.
Submission process.
Error messages.
Acknowledgement format.
Omnichannel Scope
The exact channels required for the first release must be confirmed.
Recommended MVP channels are:
In-application notification.
Email.
Single-User Assignment
The partner should confirm whether:
One user receives all alerts.
One user is assigned per product.
One primary user and one backup user are required.
Alerts must escalate if no action is taken.

9. Additional Inputs Required From the Partner
Before the product scope and prototype are finalised, the partner should provide:
The list of four pilot products.
Brand names, generic names, ingredients and APIs.
Product and molecule synonyms.
The preferred literature-search frequency.
Example search strings currently used manually.
Example literature-detection reports.
Example regulatory-reporting formats.
The required CDSCO XML sample or specification.
The applicable regulatory gateway.
A sample submission workflow.
Alert-priority definitions.
Expected review turnaround times.
The nominated pilot user.
The meaning of PVH.
Clarification of “invalid.”
Clarification of “sub-standard subpoenas.”
The decision criteria for submission versus storage.
Expected dashboard metrics.
Trial duration.
Expected pilot success criteria.

10. Revised Product Positioning
The application should be positioned as:
An AI-assisted pharmacovigilance literature-monitoring platform that continuously searches medical literature, identifies potential safety information, alerts the responsible user, generates structured detection reports and maintains an audit-ready record—without removing human control over regulatory decisions.
For pharmaceutical companies:
Maintain a consistent literature-monitoring process without building a large internal team or relying on spreadsheets and manual searches.
For third-party pharmacovigilance providers:
Manage literature monitoring for multiple pharmaceutical clients through a standardised, traceable and scalable platform.
The commercial proposition should combine:
Compliance support.
Reduced manual effort.
Faster identification of potential safety information.
Standardised reporting.
Inspection readiness.
Flexible internal-use and managed-service models.