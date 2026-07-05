const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, PageBreak,
        HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType, LevelFormat,
        PageOrientation, ExternalHyperlink, VerticalAlign } = require('docx');
const fs = require('fs');

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: "Arial", size: 22 } // 11pt
      }
    },
    paragraphStyles: [
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: "1F4E78" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 }
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "2E5C8A" },
        paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 1 }
      },
      {
        id: "Heading3",
        name: "Heading 3",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: "2E5C8A" },
        paragraph: { spacing: { before: 120, after: 80 }, outlineLevel: 2 }
      }
    ]
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } }
          }
        ]
      }
    ]
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      children: [
        // Title
        new Paragraph({
          children: [new TextRun({ text: "CostOptimizeRecommender", bold: true, size: 40, color: "1F4E78" })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 120 }
        }),
        new Paragraph({
          children: [new TextRun({ text: "System Architecture Document", size: 28, color: "2E5C8A" })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 240 }
        }),
        new Paragraph({
          children: [new TextRun({ text: "Enterprise FinOps Platform", italics: true, size: 24 })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 480 }
        }),

        // Document Info
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2340, 7020],
          rows: [
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Version", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 7020, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("1.0")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Date", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 7020, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("July 2026")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Audience", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 7020, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Development Team, Stakeholders, New Team Members")] })]
                })
              ]
            })
          ]
        }),
        new Paragraph({ children: [new TextRun("")], spacing: { after: 360 } }),

        // Executive Summary
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Executive Summary")]
        }),
        new Paragraph({
          children: [new TextRun("CostOptimizeRecommender is an enterprise FinOps platform designed to provide organizations with centralized Azure cost visibility, resource inventory management, and actionable optimization recommendations. The platform integrates with Azure Cost Management APIs and Azure Resource Manager to deliver real-time cost insights and optimization guidance grounded in actual billed costs.")],
          spacing: { after: 200 }
        }),
        new Paragraph({
          children: [new TextRun("The system follows a modern three-tier architecture with a React-based frontend, FastAPI backend, and PostgreSQL database persistence. It supports optional Kubernetes telemetry through an in-cluster agent and provides enterprise-grade security with JWT authentication and role-based access control.")],
          spacing: { after: 360 }
        }),

        // System Overview
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("System Overview")]
        }),
        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Business Purpose")]
        }),
        new Paragraph({
          children: [new TextRun("The platform serves organizations requiring:")],
          spacing: { after: 120 }
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Centralized Azure cost visibility and budget tracking")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Comprehensive inventory coverage across major Azure resource types")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Actionable optimization recommendations with estimated savings")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Secure JWT-based authentication with role-based access control")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Historical data persistence for trending and analysis")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("FinOps portal for cost exploration and recommendations")],
          spacing: { after: 240 }
        }),

        // Architecture Layers
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Architecture Overview")]
        }),
        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Three-Tier Architecture")]
        }),
        new Paragraph({
          children: [new TextRun("The platform implements a classic three-tier architecture:")],
          spacing: { after: 120 }
        }),

        // Architecture Diagram Table
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [3120, 6240],
          rows: [
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 3120, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Layer", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 6240, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Description", bold: true })] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 3120, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Presentation Layer")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 6240, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("React SPA providing user interface for cost exploration, inventory management, and recommendations")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 3120, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Application Layer")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 6240, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("FastAPI backend providing REST APIs, business logic, Azure integrations, and optimization engine")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 3120, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Data Layer")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 6240, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("PostgreSQL database for persistent storage of costs, inventory, findings, and operational data")] })]
                })
              ]
            })
          ]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        // Frontend Architecture
        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Frontend Architecture")]
        }),
        new Paragraph({
          children: [new TextRun("Technology Stack:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("React (modern UI framework)")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Node.js 18+ for build tooling")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("CSS and modern CSS frameworks")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("React Context for state management")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Custom hooks for reusable logic")],
          spacing: { after: 120 }
        }),
        new Paragraph({
          children: [new TextRun("Key Features:")],
          spacing: { before: 120 }
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Navigation driven by appRegistry.js configuration")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Dashboard for cost overview and KPIs")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Cost Explorer for time-series analysis")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Resource Inventory pages for each Azure resource type")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Recommendations page displaying optimization findings")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Admin tools for optimization runs, engine configuration, settings, and user management")],
          spacing: { after: 240 }
        }),

        // Backend Architecture
        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Backend Architecture")]
        }),
        new Paragraph({
          children: [new TextRun("Technology Stack:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Python 3.13 with FastAPI framework")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("SQLAlchemy 2.0 for ORM and database abstraction")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("PostgreSQL for persistent data storage")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Alembic for database migrations")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Uvicorn as ASGI server")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Azure SDK libraries for API integration")],
          spacing: { after: 360 }
        }),

        // Page break
        new Paragraph({ children: [new PageBreak()] }),

        // Core Components
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Core Components")]
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Azure Integration Layer")]
        }),
        new Paragraph({
          heading: HeadingLevel.HEADING_3,
          children: [new TextRun("Cost Management Integration")]
        }),
        new Paragraph({
          children: [new TextRun("Queries Azure Cost Management API (v2024-08-01) for actual billed costs using Managed Identity. Retrieves cost data at subscription and resource-group levels with support for multiple time periods and filtering options.")]
        }),
        new Paragraph({
          spacing: { after: 120 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_3,
          children: [new TextRun("Azure Resource Manager Integration")]
        }),
        new Paragraph({
          children: [new TextRun("Enumerates and inventories Azure resources across major types: VMs, disks, AKS clusters, storage accounts, databases, networking, App Service, Key Vault, and aggregate page resources. Supports both live queries and cached data from PostgreSQL.")]
        }),
        new Paragraph({
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Optimization Engine")]
        }),
        new Paragraph({
          children: [new TextRun("A configurable rule-based analysis system that evaluates Azure resources against defined optimization policies. Key features:")],
          spacing: { after: 120 }
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Rule-based findings with configurable thresholds")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Savings estimates derived from actual billed cost baselines")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Per-resource type sub-engines for specialized analysis")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Configurable engine profiles enabling/disabling rules")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Finding history tracking and remediation status management")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Findings deduplication to eliminate redundant recommendations")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Authentication & Authorization")]
        }),
        new Paragraph({
          children: [new TextRun("JWT-based authentication system with the following characteristics:")],
          spacing: { after: 120 }
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Token-based access at /api/auth/login endpoint")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Rate limiting on login endpoint")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Role-based access control (Admin and Viewer roles)")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Admin-gated endpoints: /optimize/analyze, /sync, /optimize, /dashboard")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Subscription-scoped access for multi-tenant deployments")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Secure settings encryption at rest in production")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Kubernetes agent authentication via shared secret token")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Database Schema")]
        }),
        new Paragraph({
          children: [new TextRun("PostgreSQL database manages the following primary entities:")]
        }),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2340, 7020],
          rows: [
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Entity", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 7020, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Purpose", bold: true })] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("CostRecord")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 7020, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Stores Azure cost data snapshots from Cost Management API")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Resource Inventory")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 7020, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Cached Azure resource inventory snapshots for fast retrieval")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("OptimizationFinding")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 7020, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Optimization findings with savings estimates and remediation status")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("OptimizationRun")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 7020, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("History of optimization analysis runs with execution details")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("EngineConfig")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 7020, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Optimization engine configuration including enabled rules and thresholds")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("K8sUtilization")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 7020, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Kubernetes cluster utilization snapshots from in-cluster agent")] })]
                })
              ]
            })
          ]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        // Kubernetes Agent
        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Kubernetes Telemetry Agent")]
        }),
        new Paragraph({
          children: [new TextRun("An optional lightweight in-cluster polling agent that:")],
          spacing: { after: 120 }
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Reads node and pod utilization metrics from metrics-server")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Sends utilization snapshots to the backend API")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Uses token-based authentication for secure communication")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Deployable as Kubernetes Pod via utilization-agent.yaml")],
          spacing: { after: 240 }
        }),

        // Page break
        new Paragraph({ children: [new PageBreak()] }),

        // Data Flow
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Data Flow Architecture")]
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Cost Data Pipeline")]
        }),
        new Paragraph({
          children: [new TextRun("Azure Cost Management API → Backend Cost Service → PostgreSQL → Frontend Cost Explorer")]
        }),
        new Paragraph({
          children: [new TextRun("The system retrieves actual billed costs from Azure, normalizes the data, stores snapshots in PostgreSQL for historical analysis, and exposes via REST APIs to the frontend for visualization and exploration.")]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Resource Inventory Pipeline")]
        }),
        new Paragraph({
          children: [new TextRun("Azure Resource Manager → Backend Resource Service → PostgreSQL → Frontend Inventory Pages")]
        }),
        new Paragraph({
          children: [new TextRun("Resource enumeration can be performed either as live queries to ARM or from cached inventory snapshots. The sync service updates the database periodically, enabling fast list views and filtered searches in the UI.")]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Optimization Analysis Pipeline")]
        }),
        new Paragraph({
          children: [new TextRun("Cost + Inventory Data → Optimization Engine → Findings → PostgreSQL → Recommendations API → Frontend UI")]
        }),
        new Paragraph({
          children: [new TextRun("The optimization engine analyzes combined cost and inventory data against configured rules, generates findings with savings estimates, deduplicates results, persists to the database, and exposes via the recommendations endpoint for frontend display.")]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Kubernetes Telemetry Pipeline")]
        }),
        new Paragraph({
          children: [new TextRun("Kubernetes Cluster → In-Cluster Agent → Backend API → PostgreSQL")]
        }),
        new Paragraph({
          children: [new TextRun("The optional K8s agent polls metrics-server for node and pod utilization metrics, converts to snapshots, and POSTs to the backend with token-based authentication. Data is stored for trend analysis and cost allocation insights.")]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        // Technology Stack
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Technology Stack")]
        }),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2340, 3510, 3510],
          rows: [
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Layer", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Technology", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Version/Details", bold: true })] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Frontend")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("React")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Single Page Application")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Frontend Build")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Node.js")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("v18 with npm")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Backend")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("FastAPI")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("v0.111.0")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Server")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Uvicorn")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("ASGI application server")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Language")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Python")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("v3.13")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Database")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("PostgreSQL")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Relational database")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("ORM")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("SQLAlchemy")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("v2.0.36")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Migrations")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Alembic")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Database schema versioning")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Auth")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("PyJWT")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("JWT token support")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Azure SDKs")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Multiple")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("azure-identity, azure-storage-blob")] })]
                })
              ]
            })
          ]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        // Page break
        new Paragraph({ children: [new PageBreak()] }),

        // Deployment & Infrastructure
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Deployment & Infrastructure")]
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Azure App Service Deployment")]
        }),
        new Paragraph({
          children: [new TextRun("Primary deployment target is Azure App Service (Linux runtime) with the following configuration:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Runtime: Python 3.13 on Linux")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Oryx build system enabled for automatic dependency installation")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Startup command: uvicorn app.main:app with configured port")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Health check endpoint: /health/live")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Frontend built during CI/CD and served as static files")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Environment configuration via App Service settings")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Deployment via Azure Pipelines with zip deploy")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Docker Containerization")]
        }),
        new Paragraph({
          children: [new TextRun("Multi-stage Dockerfile provides containerized deployment option:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Stage 1: React frontend build (Node 18 base)")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Stage 2: Python runtime with frontend artifacts")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Final image exposes port 8000")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Non-root app user for security")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Health check configured")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Kubernetes Deployment")]
        }),
        new Paragraph({
          children: [new TextRun("Kubernetes configuration files in /k8s/ directory support:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Deployment manifests for main application")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("In-cluster telemetry agent deployment")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Service definitions for networking")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("ConfigMaps for configuration management")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Secrets for sensitive credentials")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("CI/CD Pipeline")]
        }),
        new Paragraph({
          children: [new TextRun("Azure Pipelines orchestrates the deployment process:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Triggered on commits to main and feature branches")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Build stage: Compiles React frontend, runs tests")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Artifact creation: Zips application with built frontend")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Deploy stage: Configures App Service and deploys zip")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Integration with terraform-connect for infrastructure updates")],
          spacing: { after: 240 }
        }),

        // Page break
        new Paragraph({ children: [new PageBreak()] }),

        // Security Architecture
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Security Architecture")]
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Authentication")]
        }),
        new Paragraph({
          children: [new TextRun("The platform implements JWT-based authentication with these characteristics:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Login endpoint at /api/auth/login requires credentials")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("JWT tokens issued with configurable expiration")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Rate limiting prevents brute force attacks")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Tokens validated on protected endpoints")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("JWT_SECRET stored securely in production environments")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Authorization")]
        }),
        new Paragraph({
          children: [new TextRun("Role-based access control restricts sensitive operations:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Admin role required for: optimization analysis, data sync, settings, user management")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Viewer role for read-only access to dashboards and reports")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Subscription-scoped access for multi-tenant environments")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Azure Integration Security")]
        }),
        new Paragraph({
          children: [new TextRun("Azure API access uses secure managed identity authentication:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Managed Identity via DefaultAzureCredential for passwordless auth")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("RBAC roles: Cost Management Reader, Resource Manager Reader")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Subscription-level scoping prevents cross-subscription access")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Data Protection")]
        }),
        new Paragraph({
          children: [new TextRun("Sensitive data protection mechanisms include:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Settings encryption at rest using SETTINGS_ENCRYPTION_KEY")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Database connections over secure connections")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("K8s agent token-based authentication")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Environment variable-based secrets management")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("CORS & Network Security")]
        }),
        new Paragraph({
          children: [new TextRun("Network security is enforced through:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Dynamic CORS middleware restricts frontend origins")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("CORS_ALLOWED_ORIGINS configurable via environment variables")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("HTTP security headers enforced")],
          spacing: { after: 240 }
        }),

        // Integration Points
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("External Integration Points")]
        }),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2340, 3510, 3510],
          rows: [
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Service", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Purpose", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Authentication", bold: true })] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Azure Cost Management API")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Retrieve billed cost data")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Managed Identity")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Azure Resource Manager")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Enumerate resources")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Managed Identity")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Kubernetes API")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Metrics collection (optional)")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Service Account")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("PostgreSQL")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Data persistence")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Connection string")] })]
                })
              ]
            })
          ]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        // Environment Configuration
        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Environment Configuration")]
        }),
        new Paragraph({
          children: [new TextRun("Key environment variables control system behavior:")]
        }),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2340, 3510, 3510],
          rows: [
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Variable", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Purpose", bold: true })] })]
                }),
                new TableCell({
                  borders,
                  shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun({ text: "Production Required", bold: true })] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("DATABASE_URL")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("PostgreSQL connection string")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Yes")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("AUTH_ENABLED")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Enable JWT authentication")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Yes (true)")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("JWT_SECRET")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("JWT token signing key")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Yes")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("SETTINGS_ENCRYPTION_KEY")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Encrypts sensitive settings")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Yes")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("K8S_AGENT_TOKEN")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("K8s agent shared secret")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Yes (if agent deployed)")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("CORS_ALLOWED_ORIGINS")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("CORS allowed origins")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Yes")] })]
                })
              ]
            }),
            new TableRow({
              children: [
                new TableCell({
                  borders,
                  width: { size: 2340, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("APP_ENV")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Environment: dev, qa, prod")] })]
                }),
                new TableCell({
                  borders,
                  width: { size: 3510, type: WidthType.DXA },
                  margins: { top: 80, bottom: 80, left: 120, right: 120 },
                  children: [new Paragraph({ children: [new TextRun("Yes (prod)")] })]
                })
              ]
            })
          ]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        // Page break
        new Paragraph({ children: [new PageBreak()] }),

        // Deployment Requirements
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Deployment Requirements")]
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Azure Prerequisites")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Azure subscription with sufficient credits")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("App Service resource group created")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("PostgreSQL flexible server or equivalent database")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Managed Identity assigned to App Service")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Azure Pipelines project with build/deploy configuration")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Azure Cost Management Reader and Reader roles assigned to identity")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("CI/CD Requirements")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("GitHub or Azure Repos repository configured")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Azure Pipelines configured with azure-pipelines.yml")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Service connection to Azure subscription")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Build agent with Node.js 18+ and Python 3.13")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Artifact storage for build outputs")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Post-Deployment Configuration")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Configure environment variables in App Service settings")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Set DATABASE_URL pointing to PostgreSQL instance")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Initialize database schema via Alembic migrations")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Create initial admin user")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Verify API health check endpoint")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Configure frontend API_URL to backend endpoint")],
          spacing: { after: 240 }
        }),

        // Performance & Scalability
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Performance & Scalability")]
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Caching Strategy")]
        }),
        new Paragraph({
          children: [new TextRun("The system implements multiple caching layers:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Database query caching with SQLAlchemy")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("HTTP cache control headers for static assets")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Resource inventory snapshots reduce ARM API calls")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Cost data batching and pagination support")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("LRU caching for frequently accessed data")],
          spacing: { after: 240 }
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Scalability Considerations")]
        }),
        new Paragraph({
          children: [new TextRun("Horizontal scaling supported through:")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Stateless FastAPI design enables multiple backend instances")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Azure App Service auto-scaling rules can distribute load")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("PostgreSQL connection pooling via SQLAlchemy")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Frontend SPA can scale to serve more concurrent users")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Pagination support prevents loading large result sets")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Asynchronous background task processing available")],
          spacing: { after: 240 }
        }),

        // Monitoring & Observability
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Monitoring & Observability")]
        }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Health Checks")]
        }),
        new Paragraph({
          children: [new TextRun("Health check endpoint /health/live provides liveness probe for orchestration platforms. Docker and Kubernetes use this endpoint to determine service health.")]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun("Logging")]
        }),
        new Paragraph({
          children: [new TextRun("Structured logging via structlog provides:")],
          spacing: { after: 120 }
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Request/response logging for API calls")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Database query logging in development")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Error tracking with context")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Performance metrics")]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun("Structured log format for easy parsing and analysis")],
          spacing: { after: 240 }
        }),

        // Appendix
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Appendix: Repository Structure")]
        }),

        new Paragraph({
          children: [new TextRun("app/\t\t— Backend FastAPI application")]
        }),
        new Paragraph({
          children: [new TextRun("  ├── main.py\t\t— Entry point with API routes")]
        }),
        new Paragraph({
          children: [new TextRun("  ├── analysis/\t\t— DB analysis orchestration")]
        }),
        new Paragraph({
          children: [new TextRun("  ├── optimizer/\t\t— Optimization engine")]
        }),
        new Paragraph({
          children: [new TextRun("  ├── resources/\t\t— Per-type resource handling")]
        }),
        new Paragraph({
          children: [new TextRun("  └── database.py\t— SQLAlchemy configuration")]
        }),
        new Paragraph({
          children: [new TextRun("frontend/\t— React single-page application")]
        }),
        new Paragraph({
          children: [new TextRun("  ├── src/")]
        }),
        new Paragraph({
          children: [new TextRun("  │   ├── App.js\t\t— Main React component")]
        }),
        new Paragraph({
          children: [new TextRun("  │   ├── api/\t\t— API client code")]
        }),
        new Paragraph({
          children: [new TextRun("  │   ├── components/\t— Reusable React components")]
        }),
        new Paragraph({
          children: [new TextRun("  │   ├── pages/\t\t— Page components")]
        }),
        new Paragraph({
          children: [new TextRun("  │   └── hooks/\t\t— Custom React hooks")]
        }),
        new Paragraph({
          children: [new TextRun("k8s/\t\t— Kubernetes manifests")]
        }),
        new Paragraph({
          children: [new TextRun("docs/\t\t— Additional documentation")]
        }),
        new Paragraph({
          children: [new TextRun("requirements.txt\t— Python dependencies")]
        }),
        new Paragraph({
          children: [new TextRun("Dockerfile\t— Container image definition")]
        }),
        new Paragraph({
          children: [new TextRun("azure-pipelines.yml — CI/CD configuration")]
        }),
        new Paragraph({ spacing: { after: 240 } }),

        // Conclusion
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun("Conclusion")]
        }),
        new Paragraph({
          children: [new TextRun("CostOptimizeRecommender is a well-architected enterprise platform that combines modern full-stack technologies with cloud-native deployment patterns. The system emphasizes security through JWT authentication and RBAC, scalability through stateless design and caching, and operational excellence through structured logging and health checks. The modular architecture allows for independent scaling of frontend, backend, and data layers, while the optional Kubernetes integration extends capabilities for containerized environments.")]
        })
      ]
    }
  ]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/sessions/wonderful-modest-mayer/mnt/CostOptimizeRecommender/ARCHITECTURE.docx", buffer);
  console.log("Architecture document created successfully!");
});
