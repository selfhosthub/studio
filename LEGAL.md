# Legal Notice and Operator Responsibility Disclaimer

## Software Framework Disclaimer

Studio is a software framework that individuals and organizations deploy and operate for their own purposes. Common use cases include personal automation, client solution delivery, and hosted SaaS platforms. By accessing, deploying, or using Studio, you acknowledge and agree to the following:

### 1. Framework, Not Managed Service

Studio is **software code**, not a managed service. The developers of Studio:
- Provide the technical framework only
- Do not operate any instances of the software
- Do not process payments on behalf of operators
- Do not have access to operator or end-user data
- Are not a party to any transactions between operators and their customers

Use of Studio is governed by the [Studio Use License](LICENSE). This document (LEGAL.md) supplements the LICENSE with operator obligations, disclaimers, and guidance. In the event of a conflict, the LICENSE governs.

### Authorship and Development Tools

Studio is developed using a combination of human authorship and AI-assisted tools, with all architectural, licensing, and policy decisions made by the human developer(s). AI tools are used solely as implementation and productivity aids and do not operate autonomously or make independent decisions regarding the design, licensing, or legal posture of the software.

### 2. Acquisition and Acceptance of Terms

The entity that downloads, installs, or connects to any software component, model file, or third-party service is the entity that accepts the associated license terms, terms of use, and conduct policies. This principle applies uniformly across the entire Studio ecosystem:

- **Studio source code** - governed by the Studio Use License
- **Third-party tools** (ComfyUI, FFmpeg, Whisper, etc.) - each governed by their own respective licenses
- **AI model files** (Flux, SDXL, SD1.5, LoRAs, VAEs, ControlNet models, etc.) - each governed by their own respective licenses
- **Third-party API services** (OpenAI, Anthropic, Google, Leonardo AI, Stripe, etc.) - each governed by their own terms of service

No party - including agencies, consultants, resellers, or any other intermediary - may deliver, transfer, or bundle these components to another party. Each deploying or consuming party must obtain them directly, through their own actions, from the applicable public distribution channels or service providers.

Agencies and consultants may guide the acquisition process, assist with configuration, and install their own workflow intellectual property (configurations, templates, field mappings, branding assets). The underlying software, tools, and models must be obtained by the client.

### 3. Permitted Uses

The LICENSE defines what you may and may not do with Studio. The following examples illustrate common permitted and prohibited uses. These examples are informational and do not modify the LICENSE.

**Solo User / Individual**

You deploy and operate Studio for your own use.

Permitted:
- Run workflows and sell the output (images, video, text, data, etc.)
- Create workflow configurations and templates and sell them
- Use basic and advanced marketplace packages on your own instance
- Modify the Software for your own use

Not permitted:
- Give others login access to your instance as a service
- Redistribute marketplace packages

**Agency / Consultant**

You build solutions for clients using Studio.

Permitted:
- Build workflows on your own instance during development
- Guide or assist clients in downloading and installing their own Studio deployment - the client must acquire the Software, third-party tools, and AI model files themselves through public distribution channels
- Install workflow configurations, templates, field mappings, and branding assets on the client's running deployment - these are your intellectual property
- Charge for consulting, installation, configuration, training, and support

Not permitted:
- Deliver, transfer, or bundle Studio source code, third-party tools (ComfyUI, FFmpeg, Whisper), or AI model files to clients - the client must download and install these components themselves, thereby accepting each component's license terms
- Redistribute advanced marketplace packages to clients via file transfer, bundled images, or any method other than direct download from the official marketplace
- Operate a single instance and sell access to multiple unrelated client organizations as a managed platform (this is the SaaS operator model - see below)
- Offer automated or templated "Studio-in-a-box" provisioning to clients

Each client who wants ongoing access to marketplace updates, new providers, or bug fixes must obtain their own marketplace membership.

**SaaS Operator**

You operate a single Studio instance and charge customers for access. As the operator, you are the entity that downloads and installs Studio, all third-party tools, and all AI model files - you accept all associated license terms and bear responsibility for compliance with each.

Permitted:
- Run a multi-tenant instance with paying customers (no customer limit)
- Curate which providers, templates, and services are available
- Build custom workflows and templates as value-add
- White-label the interface with your own branding
- Charge subscription fees for access

Not permitted:
- Offer automated provisioning of separate Studio instances for each customer (that is platform-as-a-service, not SaaS)
- Create and distribute pre-configured Studio containers or deployment packages
- Redistribute marketplace packages outside your own instance

**Prohibited: Instance Vending / Platform-as-a-Service**

The following are prohibited under the LICENSE regardless of how they are described:
- Building a platform whose primary function is deploying Studio instances for third parties
- Selling or distributing pre-configured Studio images, containers, or infrastructure templates
- Offering "one-click deploy" or automated self-service provisioning of Studio to third parties
- Forking or rebranding Studio for resale as a competing product

The distinction the LICENSE draws is between **operating** and **distributing**. You may build a business that runs on Studio. You may not build a business that distributes Studio.

### 4. Operator Responsibility

By deploying Studio, operators assume **full and sole responsibility** for the following (where applicable):

**Legal Compliance:**
- Compliance with all applicable laws and regulations in their jurisdiction
- ROSCA, FTC, and state-level subscription billing laws (United States)
- GDPR, CCPA, and other data protection regulations
- CAN-SPAM, CASL, and email marketing laws
- PCI-DSS compliance (maintained through hosted checkout usage)
- Tax collection, reporting, and remittance
- Any industry-specific regulations (HIPAA, FINRA, etc.)

**Customer Relationships:**
- Terms of service for end users
- Privacy policy and data handling disclosures
- Customer support and dispute resolution
- Subscription billing disclosures and consent
- Cancellation mechanisms and confirmations
- Transactional and marketing communications

**Technical Operations:**
- Server security and maintenance
- Data backup and recovery
- Incident response and breach notification
- Access control and authentication policies
- Encryption and data protection

### 5. Third-Party Services, APIs, and AI/LLM Usage

Studio enables operators to integrate with external APIs, applications, and AI/LLM services (including but not limited to OpenAI, Anthropic Claude, Google Gemini, Leonardo.AI, Stripe, Notion, and others). **Operators bear full and sole responsibility for:**

**Licensing and Terms of Service:**
- Reading, understanding, and complying with the terms of service, acceptable use policies, and licensing agreements of every third-party service they connect through Studio
- Ensuring their use case is permitted under each provider's terms (including commercial use, resale, sub-licensing, and redistribution)
- Monitoring for changes to third-party terms that may affect their usage

**AI/LLM-Specific Obligations:**
- Complying with AI model providers' usage policies, including restrictions on prohibited content, high-risk use cases, and output attribution requirements
- Understanding and communicating to end users any limitations on AI-generated content ownership, licensing, or commercial use rights as defined by the model provider
- Adhering to any requirements around disclosure of AI-generated content to end users or downstream consumers
- Complying with provider-specific data handling, retention, and training opt-out policies

**API Keys and Credentials:**
- Securing and safeguarding all API keys, tokens, and credentials used within Studio
- Ensuring API keys are not shared, exposed, or used in violation of the issuing provider's terms
- Managing API usage within rate limits, quotas, and spending caps set by each provider
- Bearing all costs associated with API usage incurred through their Studio instance

**Content and Output:**
- Ensuring that content generated through third-party services (images, text, video, audio) is used in compliance with the generating service's output licensing terms
- Verifying that generated content does not infringe on third-party intellectual property rights
- Complying with any attribution, watermarking, or labeling requirements imposed by service providers

**Data Sharing:**
- Understanding what data is transmitted to third-party services when workflows execute
- Ensuring that data sent to external APIs complies with their data processing agreements and the operator's own privacy obligations to end users
- Obtaining any necessary consent from end users before their data is processed by third-party services

**Self-Hosted Tools and Model Files (ComfyUI, FFmpeg, etc.):**

Studio integrates with self-hosted tools such as ComfyUI, FFmpeg, and Whisper that operators install and run on their own infrastructure. Operators bear full and sole responsibility for:

- Downloading, installing, and configuring these tools and any required model files (e.g., Flux, Stable Diffusion XL, SD1.5, LoRAs, VAEs, ControlNet models, upscalers, and other checkpoint or auxiliary files)
- Reading and complying with the specific license of every model file they download and use - these licenses vary significantly (e.g., Stability AI's community license, Black Forest Labs' Flux licenses, CreativeML OpenRAIL-M, Apache 2.0, and others) and may impose restrictions on commercial use, redistribution, content generation, or attribution
- Ensuring that their intended use (commercial, non-commercial, SaaS redistribution, etc.) is permitted under each model's license terms
- Complying with any output attribution, usage restrictions, or content policy requirements imposed by model creators
- Securing and maintaining self-hosted infrastructure running these tools
- Verifying the integrity and provenance of model files obtained from third-party sources (e.g., HuggingFace, CivitAI, or other repositories)

Studio does not distribute, bundle, or provide any model files, AI checkpoints, or third-party tool binaries. Studio provides only the integration layer to orchestrate these tools - the operator is solely responsible for obtaining, licensing, and operating them.

The developers of Studio do not hold, manage, or have visibility into operator API keys or third-party service accounts. Studio merely provides the technical mechanism to configure and invoke these services - all contractual relationships with third-party providers are solely between the operator and those providers.

### 6. Marketplace Packages

The Studio Marketplace provides optional provider packages, services, and templates that extend Studio's capabilities. These packages are licensed separately from the Studio platform under their own terms (the Marketplace Terms of Service).

**Operators and users are responsible for:**
- Complying with the Marketplace Terms of Service for any packages they install
- Obtaining marketplace packages only through the official marketplace distribution channel
- Not redistributing, sideloading, bundling, or transferring marketplace packages to other deployments
- Understanding that marketplace membership and package access are non-transferable

Workflow configurations that reference marketplace packages may be freely shared or sold. The marketplace packages themselves may not be redistributed. A recipient of a shared workflow must obtain the required marketplace packages independently.

### 7. No Professional Advice

Nothing in Studio's documentation, code, or communications constitutes:
- **Legal advice** - Consult a qualified attorney for legal matters
- **Tax or accounting advice** - Consult a CPA or tax professional for tax obligations
- **Financial advice** - Consult a financial advisor for business financial decisions

The compliance documentation provided is:
- Informational only
- Not a substitute for professional counsel
- Not guaranteed to be complete or current
- Not tailored to any specific jurisdiction or business

**Operators should consult with qualified professionals** (legal, tax, financial) regarding their specific obligations.

### 8. Limitation of Liability

To the maximum extent permitted by applicable law:

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT.

IN NO EVENT SHALL THE AUTHORS, COPYRIGHT HOLDERS, OR DEVELOPERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This includes, but is not limited to:
- Regulatory fines or penalties incurred by operators
- Chargebacks, disputes, or payment processor actions
- Data breaches or security incidents at operator instances
- Customer complaints or legal actions against operators
- Loss of revenue, data, or business opportunities
- Fees, penalties, or account suspensions imposed by third-party service providers due to operator misuse
- Claims arising from AI-generated content produced through operator workflows

### 9. Indemnification

By using Studio, operators agree to indemnify and hold harmless the developers and contributors from any claims, damages, losses, or expenses (including legal fees) arising from:
- Operator's use of the software
- Operator's failure to comply with applicable laws
- Operator's relationships with their end users
- Operator's use of or failure to comply with third-party service terms, API licenses, or AI/LLM usage policies
- Any modifications made to the software by the operator

### 10. Jurisdiction

This disclaimer shall be governed by and construed in accordance with applicable laws, without regard to conflict of law principles.

---

## For Operators

If you are deploying Studio to run a business:

1. **Read the [Studio Use License](LICENSE)** to understand what is permitted
2. **Get professional counsel** (legal, tax, financial) before going live with paying customers
3. **Read the [Super Admin Guide](super-admin.md)** for deployment and compliance considerations
4. **Review the terms of service** for every third-party API and AI/LLM provider you integrate
5. **Configure your instance** with appropriate terms, privacy policy, and disclosures
6. **Set up proper communications** for subscription lifecycle events
7. **Maintain backups** and incident response procedures
8. **Communicate to end users** any relevant restrictions on AI-generated content from upstream providers

---

**Last Updated:** 2026-02-13