"""Verbatim AI FDE tool specifications and instructions, captured from the live UI.

Do not edit by hand: ``TOOL_SPECS_JSON`` is the exact JSON the AI FDE UI sent
to ``PUT /language-model-service/api/llm/v3/completion/GPT_5_6_SOL/
streamCompletionChunk`` in the richest captured request (170 input items, 72
tools) from the 2026-09-04 CDP capture of a live Foundry deployment
(/tmp/ai-fde-richest-request.json), cross-checked against the
``/tmp/tool-load-documentation.json`` artifact. This module holds only the
MVP subset the CLI agent loop registers; the captured request carried 72.

``CAPTURED_INSTRUCTIONS_PREFIX`` is the captured instructions block truncated
just before the session-specific lines (the run date, the current user ID,
and the deployment-specific <available_skills> block); the loop appends the
run date at request time and deliberately does NOT fabricate a user ID or a
skill catalog.
"""

import json

TOOL_SPECS_JSON = r"""{
 "load_documentation": {
  "function": {
   "name": "load_documentation",
   "description": "Loads a set of individual documentation pages.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "pageIds": {
      "type": "array",
      "items": {
       "type": "string"
      },
      "description": "Array of documentation page IDs to load."
     }
    },
    "required": [
     "pageIds"
    ],
    "additionalProperties": false
   },
   "strict": true
  },
  "type": "function"
 },
 "load_documentation_bundles": {
  "function": {
   "name": "load_documentation_bundles",
   "description": "Loads a set of documentation bundles. Prefer loading documentation bundles before loading individual documentation pages.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "documentationBundles": {
      "type": "array",
      "items": {
       "type": "string",
       "enum": [
        "workshop-product-design",
        "data-integration-core",
        "data-integration-api-reference",
        "data-integration-incremental",
        "data-integration-testing-expectations",
        "data-integration-unstrucutured-data",
        "data-integration-document-extraction",
        "data-integration-polars",
        "data-integration-pyspark",
        "data-integration-external-transforms",
        "data-integration-cipher",
        "data-integration-time-series",
        "data-integration-language-models",
        "ontology-core",
        "ontology-object-types",
        "ontology-link-types",
        "ontology-action-types",
        "ontology-interfaces",
        "ontology-ciphertext-properties",
        "functions-core",
        "functions-testing",
        "functions-typescript-v1",
        "functions-python",
        "functions-document-extraction",
        "functions-ontology-edits-tsv1",
        "functions-ontology-edits-tsv2",
        "functions-ontology-edits-python",
        "functions-using-embeddings-and-language-models",
        "modeling-no-code-model-authoring",
        "modeling-pro-code-model-authoring",
        "modeling-transforms",
        "functions-external-tsv1",
        "functions-external-tsv2",
        "functions-external-python",
        "function-backed-columns",
        "function-backed-charts",
        "functions-notifications",
        "osdk-react-applications",
        "osdk-react-widget-sets",
        "functions-vertex",
        "functions-kairos",
        "functions-ciphertext",
        "governance-general",
        "governance-permissions",
        "data-connection-core",
        "observability-debugging"
       ]
      },
      "description": "Array of documentation bundles to load."
     }
    },
    "required": [
     "documentationBundles"
    ],
    "additionalProperties": false
   },
   "strict": true
  },
  "type": "function"
 },
 "ontology_sql_query": {
  "function": {
   "name": "ontology_sql_query",
   "description": "Run a SQL query on object types and link types in the ontology. Prefer this tool to dataset_sql_query when working with ontology objects.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "queries": {
      "type": "array",
      "items": {
       "type": "object",
       "properties": {
        "query": {
         "type": "string",
         "description": "\nQuery the ontology as a relational DB: object type = table, property = column, link type = JOIN hint. Reference every table by its alias and every column by an exact property apiName from discovery tools. The dialect is a strict subset of ANSI-compatible Spark SQL validated by Apache Calcite \u2014 SELECT/WITH only, read-only; many valid Spark constructs are rejected.\n\nBacktick every table/column; single-quote string literals: `status` = 'ACTIVE'. For dates/timestamps use TYPED literals, never a bare string: `hireDate` >= DATE '2023-01-01', `createdAt` >= TIMESTAMP '2023-01-15 10:30:00' \u2014 a bare date/time string can silently match zero rows.\n\nIndex model: a Lucene-style index, not a row store. WHERE/ORDER BY/LIMIT push into the index only on raw stored properties. Wrapping a column in a function, arithmetic, CAST, CONCAT, or date math drops the index \u2014 rows filter in memory (slow, can exhaust the row budget). So, when the query allows:\n- Favor raw properties in WHERE/ORDER BY: <example_good>`hireDate` >= DATE '2023-01-01'</example_good> is cheaper than <example_bad>YEAR(`hireDate`)=2023</example_bad>; <example_good>`status`='ACTIVE'</example_good> than <example_bad>UPPER(`status`)='ACTIVE'</example_bad>; <example_good>ORDER BY `priority`</example_good> than <example_bad>`priceA`+`priceB`</example_bad>.\n- Keeping math on the literal side lets it fold to a constant: <example_good>`salary` > 100000/12</example_good> is cheaper than <example_bad>`salary`*12 > 100000</example_bad>.\n- Shaping functions (CONCAT, DATE_FORMAT, rounding) are cheapest in the final SELECT, after filtering \u2014 but use them wherever the query needs them.\n- Aggregations can be cheap when done over native properties; pre-aggregate in a subquery when that's the case.\n- Row order is undefined without ORDER BY.\n\nMany-to-many links: query the link's relation RID directly as a join table (backtick it \u2014 it contains dots). The join table has two foreign-key columns whose names come from the link's configured API names; the column name does NOT reliably indicate which object's keys it holds, so don't guess. First inspect a sample row to learn the real columns and which side each holds:\n  SELECT * FROM `ri.ontology.main.relation.0` AS lt\nRead the values (e.g. 'person-001' vs 'car-001') to see which column holds which object's keys. Then join the column holding the target's keys to the target table and filter on the column holding the source's keys. If the columns are `car_linkedCars` (holding Person keys) and `person_linkedDrivers` (holding Car keys), get one person's cars:\n  SELECT c.`carId`, c.`carName`\n  FROM `ri.ontology.main.relation.0` AS lt\n  INNER JOIN `Car` AS c ON c.`carId` = lt.`person_linkedDrivers`\n  WHERE lt.`car_linkedCars` = 'person-001';\n\nSupported (this is the whole surface \u2014 anything not listed is likely rejected):\n- Filters: = != < <= > >=, IN, NOT IN, BETWEEN, IS [NOT] NULL, AND/OR/NOT, LIKE/RLIKE (only on a literal, no col LIKE col), ARRAY_CONTAINS.\n- Joins: INNER and LEFT [OUTER] only, on EQUALS/AND/OR predicates.\n- Set ops: UNION, UNION ALL, EXCEPT.\n- Aggregation (GROUP BY): COUNT, COUNT(DISTINCT one column), SUM, AVG, MIN, MAX, STDDEV_POP, STDDEV_SAMP, COLLECT.\n- Window (OVER): ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD, FIRST_VALUE, LAST_VALUE, NTH_VALUE, SUM, MIN, MAX, COUNT.\n- Scalar (SELECT): + - * / MOD, ABS, ROUND, CEIL, FLOOR, POWER, GREATEST, LEAST; UPPER, LOWER, SUBSTRING, LEFT, CONCAT (||, not CONCAT_WS), REPLACE, REGEXP_REPLACE, REGEXP_EXTRACT, LENGTH, TRIM; CAST, CASE; CURRENT_DATE, CURRENT_TIMESTAMP, DATE_ADD, DATE_SUB, DATEDIFF, DATE_TRUNC, DATE_FORMAT, EXTRACT (only YEAR/MONTH/DAY/QUARTER).\n- Array columns: ARRAY(...), element[i] (0-based), CARDINALITY, ARRAY_JOIN, EXPLODE, ARRAY_CONTAINS.\n\nRejected (valid Spark, rejected here):\n- Use typed literal or CAST instead of to_date/to_timestamp.\n- Aggregation: no FILTER clause, no multi-column COUNT(DISTINCT), no agg/group over array columns.\n- Window: no AVG/NTILE OVER, no DISTINCT/EXCLUDE, integer frame offsets only.\n- No RIGHT/FULL/ASOF/CROSS joins, correlated subqueries, INTERSECT, EXCEPT ALL, or recursive CTEs.\n- Structs: sub-fields one level deep only, don't select a whole struct. OFFSET needs LIMIT; OFFSET+LIMIT <= 10000.\n\nOutput: one page, capped at the first 100 rows; a count equal to the limit likely means truncation. It is generally better to FILTER and LIMIT to avoid queries that scan a whole large table.\n\n<example_good description=\"aggregate in a subquery, then join; raw filter and sort pushed down, shaping in outer SELECT\">\nSELECT\n  p.`planName`,\n  CASE WHEN o.`objectiveCount` >= 10 THEN 'large' ELSE 'small' END AS `size`\nFROM `Plan` p\nJOIN (\n  SELECT `planId`, COUNT(`objectiveId`) AS `objectiveCount`\n  FROM `Objective`\n  GROUP BY `planId`\n) o ON o.`planId` = p.`planId`\nWHERE p.`status` = 'ACTIVE'\nORDER BY p.`planName` LIMIT 100;\n</example_good>\n"
        },
        "ontologyBranchRid": {
         "description": "The ontology branch RID to run the ontology SQL query on. Will use the default branch if not provided.",
         "anyOf": [
          {
           "type": "string"
          },
          {
           "type": "null"
          }
         ]
        }
       },
       "required": [
        "query",
        "ontologyBranchRid"
       ],
       "additionalProperties": false
      }
     },
     "sources": {
      "type": "array",
      "items": {
       "type": "object",
       "properties": {
        "alias": {
         "type": "string",
         "description": "The alias used to reference this source in the SQL query."
        },
        "source": {
         "anyOf": [
          {
           "type": "object",
           "properties": {
            "type": {
             "type": "string",
             "const": "objectType"
            },
            "objectTypeRid": {
             "description": "RID format: ri.ontology.main.object-type.{UUID}",
             "type": "string"
            }
           },
           "required": [
            "type",
            "objectTypeRid"
           ],
           "additionalProperties": false,
           "description": "Represents all objects for the given object type."
          },
          {
           "type": "object",
           "properties": {
            "type": {
             "type": "string",
             "const": "referencedObjectSet"
            },
            "objectSetRid": {
             "description": "RID format: ri.object-set.main.object-set.{UUID}, ri.object-set.main.versioned-object-set.{UUID}, or ri.object-set.main.temporary-object-set.{UUID}",
             "type": "string"
            }
           },
           "required": [
            "type",
            "objectSetRid"
           ],
           "additionalProperties": false,
           "description": "Represents a specific set of objects."
          }
         ]
        }
       },
       "required": [
        "alias",
        "source"
       ],
       "additionalProperties": false
      }
     }
    },
    "required": [
     "queries",
     "sources"
    ],
    "additionalProperties": false
   },
   "strict": true
  },
  "type": "function"
 },
 "list_evaluation_runs": {
  "function": {
   "name": "list_evaluation_runs",
   "description": "List evaluation runs for a given evaluation suite",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "evaluationSuiteRid": {
      "type": "string",
      "description": "The RID of the evaluation suite to list runs for"
     },
     "pageToken": {
      "description": "Token for pagination to get next page of results",
      "anyOf": [
       {
        "type": "string"
       },
       {
        "type": "null"
       }
      ]
     }
    },
    "required": [
     "evaluationSuiteRid",
     "pageToken"
    ],
    "additionalProperties": false
   },
   "strict": true
  },
  "type": "function"
 },
 "load_evaluation_runs": {
  "function": {
   "name": "load_evaluation_runs",
   "description": "Load one or more evaluation runs with their summary data including pass/fail counts and aggregated metrics. Use this after discovering runs with list_evaluation_runs.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "evaluationSuiteRid": {
      "type": "string",
      "description": "The RID of the evaluation suite"
     },
     "executionIds": {
      "type": "array",
      "items": {
       "type": "string"
      },
      "description": "The execution IDs of the runs to load"
     }
    },
    "required": [
     "evaluationSuiteRid",
     "executionIds"
    ],
    "additionalProperties": false
   },
   "strict": true
  },
  "type": "function"
 },
 "get_test_case_results": {
  "function": {
   "name": "get_test_case_results",
   "description": "Get detailed test case execution results for an evaluation run. Returns individual test case outcomes, inputs, outputs, metric values, debug outputs, and failure details. Use after load_evaluation_runs to drill down into specific test results.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "evaluationSuiteRid": {
      "type": "string",
      "description": "The RID of the evaluation suite"
     },
     "executionId": {
      "type": "string",
      "description": "The execution ID of the run to fetch test case results for"
     },
     "pageToken": {
      "description": "Token for pagination to get next page of results",
      "anyOf": [
       {
        "type": "string"
       },
       {
        "type": "null"
       }
      ]
     },
     "pageSize": {
      "description": "Max number of test cases per page",
      "anyOf": [
       {
        "type": "number",
        "minimum": 1,
        "maximum": 50
       },
       {
        "type": "null"
       }
      ]
     }
    },
    "required": [
     "evaluationSuiteRid",
     "executionId",
     "pageToken",
     "pageSize"
    ],
    "additionalProperties": false
   },
   "strict": true
  },
  "type": "function"
 },
 "get_evaluation_suite_definition": {
  "function": {
   "name": "get_evaluation_suite_definition",
   "description": "Returns the current test cases and evaluators of an evaluation suite, as well as the target schema for reference. The branch resolves the target only; the evaluation suite resource itself is not branched. Only TypeScript V1 Function targets support branch-specific versions. If a TypeScript V1 Function has no version on the selected branch, the resolved version may be from main. For TypeScript V2 and Python Function targets, only main is used. The target is also returned as a context item.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "evaluationSuiteRid": {
      "type": "string",
      "description": "The RID of the evaluation suite to retrieve"
     },
     "branch": {
      "anyOf": [
       {
        "type": "object",
        "properties": {
         "globalBranchRid": {
          "type": "string",
          "description": "A global branch RID in the format ri.branch..branch.{UUID}. Use create_global_branch to get a global branch RID (if available)."
         }
        },
        "required": [
         "globalBranchRid"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "ontologyBranchRid": {
          "type": "string",
          "description": "An Ontology branch RID in the format ri.ontology.main.branch.{UUID}. Use create_global_branch to get an Ontology branch RID (if available)."
         }
        },
        "required": [
         "ontologyBranchRid"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "codeRepositoryBranchName": {
          "type": "string",
          "description": "Either the code repository branch name of a global branch or the branch name of a local code repository branch. Prefer using globalBranchRid if possible."
         }
        },
        "required": [
         "codeRepositoryBranchName"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "mainBranch": {
          "type": "boolean",
          "const": true,
          "description": "Resolves the main branch."
         }
        },
        "required": [
         "mainBranch"
        ],
        "additionalProperties": false
       }
      ],
      "description": "The global branch used only to resolve the suite's target schema. The evaluation suite itself is not branched. Only TypeScript V1 Function targets support branch-specific versions. If a TypeScript V1 Function has no version on the selected branch, the resolved version may be from main. For TypeScript V2 and Python Function targets, only main is used."
     }
    },
    "required": [
     "evaluationSuiteRid",
     "branch"
    ],
    "additionalProperties": false
   },
   "strict": true
  },
  "type": "function"
 },
 "run_evaluation_suite": {
  "function": {
   "name": "run_evaluation_suite",
   "description": "Run an evaluation suite against its configured target function.\n- Requires the suite RID, a branch, and a mapping from target input names to test case parameter names\n- The target will be resolved to the latest version on the specified branch. Only TypeScript V1 Function targets support branch-specific versions. If a TypeScript V1 Function has no version on the selected branch, the resolved version may be from main. For TypeScript V2 and Python Function targets, only main is used.\n- Use get_evaluation_suite_definition first to understand the suite's inputs and parameters\n- For project-scoped runs, call get_evaluation_suite_project_scope_readiness first and resolve any missing project imports before running\n- For Logic targets, forceTargetsToExecuteInProjectScopedMode is a separate opt-in. Leave it unset unless the user explicitly asks to override the target's own execution mode.\n- Static inputs can be provided for target inputs that should use a fixed value instead of a test case parameter\n- Use experiments only when the user wants to compare the same suite across multiple values for one or more target inputs, such as model function inputs, temperature settings, or other target parameters. For normal suite runs, leave experiment unset.\n- To run an experiment, provide experiment.parameters as the value grid. AI FDE runs every Cartesian product, tags the runs with shared experiment metadata, and returns all execution IDs.\n- The suite must have exactly one execution target configured, and that target must be a Logic or a function\n- Returns execution IDs. After the build jobs complete, use load_evaluation_runs with the returned execution IDs to view results.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "evaluationSuiteRid": {
      "type": "string",
      "description": "The RID of the evaluation suite to run"
     },
     "branch": {
      "anyOf": [
       {
        "type": "object",
        "properties": {
         "globalBranchRid": {
          "type": "string",
          "description": "A global branch RID in the format ri.branch..branch.{UUID}. Use create_global_branch to get a global branch RID (if available)."
         }
        },
        "required": [
         "globalBranchRid"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "ontologyBranchRid": {
          "type": "string",
          "description": "An Ontology branch RID in the format ri.ontology.main.branch.{UUID}. Use create_global_branch to get an Ontology branch RID (if available)."
         }
        },
        "required": [
         "ontologyBranchRid"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "codeRepositoryBranchName": {
          "type": "string",
          "description": "Either the code repository branch name of a global branch or the branch name of a local code repository branch. Prefer using globalBranchRid if possible."
         }
        },
        "required": [
         "codeRepositoryBranchName"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "mainBranch": {
          "type": "boolean",
          "const": true,
          "description": "Resolves the main branch."
         }
        },
        "required": [
         "mainBranch"
        ],
        "additionalProperties": false
       }
      ],
      "description": "The global branch to resolve evaluation targets on. Logic targets use the latest saved Logic version on the branch. Only TypeScript V1 Function targets support branch-specific versions. If a TypeScript V1 Function has no version on the selected branch, the resolved version may be from main. For TypeScript V2 and Python Function targets, only main is used."
     },
     "parameterMappings": {
      "type": "array",
      "items": {
       "type": "object",
       "properties": {
        "targetInputName": {
         "type": "string",
         "description": "Name of a target input"
        },
        "testCaseParameterName": {
         "type": "string",
         "description": "Name of a test case parameter to map to this input"
        }
       },
       "required": [
        "targetInputName",
        "testCaseParameterName"
       ],
       "additionalProperties": false
      },
      "description": "Mapping from target input names to test case parameter names."
     },
     "staticInputs": {
      "description": "Optional list of target inputs that should use a static literal value instead of a test case parameter.",
      "anyOf": [
       {
        "type": "array",
        "items": {
         "type": "object",
         "properties": {
          "targetInputName": {
           "type": "string",
           "description": "Name of a target input"
          },
          "value": {
           "$ref": "#/$defs/__schema0"
          }
         },
         "required": [
          "targetInputName",
          "value"
         ],
         "additionalProperties": false
        }
       },
       {
        "type": "null"
       }
      ]
     },
     "experiment": {
      "description": "Optional experiment configuration for running the suite once per combination of target input values. Each target input listed here must not also appear in parameterMappings or staticInputs. At most 25 run combinations are allowed.",
      "anyOf": [
       {
        "type": "object",
        "properties": {
         "name": {
          "description": "Optional experiment name. A unique suffix will be added to group the generated runs.",
          "anyOf": [
           {
            "type": "string"
           },
           {
            "type": "null"
           }
          ]
         },
         "parameters": {
          "type": "array",
          "items": {
           "type": "object",
           "properties": {
            "targetInputName": {
             "type": "string",
             "description": "Name of a target input controlled by the experiment"
            },
            "values": {
             "type": "array",
             "items": {
              "$ref": "#/$defs/__schema0"
             },
             "description": "Literal values to try for this target input."
            }
           },
           "required": [
            "targetInputName",
            "values"
           ],
           "additionalProperties": false
          },
          "description": "Hyperparameter grid. Every Cartesian product of these values will be run."
         }
        },
        "required": [
         "parameters",
         "name"
        ],
        "additionalProperties": false
       },
       {
        "type": "null"
       }
      ]
     },
     "timesToRunEachTest": {
      "description": "Number of times to run each test case (1-10, default 1).",
      "anyOf": [
       {
        "type": "number",
        "minimum": 1,
        "maximum": 10
       },
       {
        "type": "null"
       }
      ]
     },
     "testCaseParallelism": {
      "description": "Number of test cases to run in parallel (1-10, default 10).",
      "anyOf": [
       {
        "type": "number",
        "minimum": 1,
        "maximum": 10
       },
       {
        "type": "null"
       }
      ]
     },
     "executionMode": {
      "description": "Execution scope. 'projectScoped' (default, recommended): results are visible to everyone with project access, persisted indefinitely, and appear in the run history dataset. 'userScoped': results are only visible to the current user, persisted for 24 hours, and do not appear in run history. Use userScoped only if the user explicitly requests it or project-scoped execution is blocked.",
      "anyOf": [
       {
        "type": "string",
        "enum": [
         "userScoped",
         "projectScoped"
        ]
       },
       {
        "type": "null"
       }
      ]
     },
     "forceTargetsToExecuteInProjectScopedMode": {
      "description": "For project-scoped runs against Logic targets, whether to override the target's own execution mode and force it to execute in project scope. Defaults to false. Only set this if the user explicitly wants that override.",
      "anyOf": [
       {
        "type": "boolean"
       },
       {
        "type": "null"
       }
      ]
     }
    },
    "required": [
     "evaluationSuiteRid",
     "branch",
     "parameterMappings",
     "staticInputs",
     "experiment",
     "timesToRunEachTest",
     "testCaseParallelism",
     "executionMode",
     "forceTargetsToExecuteInProjectScopedMode"
    ],
    "additionalProperties": false,
    "$defs": {
     "__schema0": {
      "anyOf": [
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "string"
         },
         "value": {
          "type": "string"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "boolean"
         },
         "value": {
          "type": "boolean"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "double"
         },
         "value": {
          "anyOf": [
           {
            "type": "number"
           },
           {
            "type": "string",
            "const": "NaN"
           }
          ]
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "float"
         },
         "value": {
          "type": "string"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "integer"
         },
         "value": {
          "type": "number"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "long"
         },
         "value": {
          "type": "number"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "short"
         },
         "value": {
          "type": "number"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "null"
         },
         "value": {
          "type": "null"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "date"
         },
         "value": {
          "type": "string"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "timestamp"
         },
         "value": {
          "type": "string"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "array"
         },
         "value": {
          "type": "array",
          "items": {
           "$ref": "#/$defs/__schema0"
          }
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "map"
         },
         "value": {
          "type": "array",
          "items": {
           "type": "object",
           "properties": {
            "key": {
             "$ref": "#/$defs/__schema0"
            },
            "value": {
             "$ref": "#/$defs/__schema0"
            }
           },
           "additionalProperties": false,
           "required": [
            "key",
            "value"
           ]
          }
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "struct"
         },
         "value": {
          "type": "array",
          "items": {
           "type": "object",
           "properties": {
            "fieldName": {
             "type": "string"
            },
            "fieldValue": {
             "$ref": "#/$defs/__schema0"
            }
           },
           "required": [
            "fieldName",
            "fieldValue"
           ],
           "additionalProperties": false
          }
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "model"
         },
         "value": {
          "anyOf": [
           {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "lmsModel"
             },
             "languageModelRid": {
              "type": "string"
             }
            },
            "required": [
             "type",
             "languageModelRid"
            ],
            "additionalProperties": false
           },
           {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "lmsRegisteredModel"
             },
             "registeredModelRid": {
              "type": "string"
             }
            },
            "required": [
             "type",
             "registeredModelRid"
            ],
            "additionalProperties": false
           },
           {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "registeredModel"
             },
             "functionRid": {
              "type": "string"
             },
             "functionVersion": {
              "type": "string"
             }
            },
            "required": [
             "type",
             "functionRid",
             "functionVersion"
            ],
            "additionalProperties": false
           }
          ]
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "objectSet"
         },
         "value": {
          "type": "string"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "objectLocator"
         },
         "objectTypeId": {
          "type": "string"
         },
         "primaryKey": {
          "anyOf": [
           {
            "type": "string"
           },
           {
            "type": "number"
           },
           {
            "type": "boolean"
           }
          ]
         }
        },
        "required": [
         "type",
         "objectTypeId",
         "primaryKey"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "objectRid"
         },
         "value": {
          "type": "string"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "unknown"
         },
         "value": {
          "type": "null"
         }
        },
        "required": [
         "type",
         "value"
        ],
        "additionalProperties": false
       }
      ]
     }
    }
   },
   "strict": true
  },
  "type": "function"
 },
 "execute_action": {
  "function": {
   "name": "execute_action",
   "description": "Executes an ontology action.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "actionTypeRid": {
      "type": "string",
      "description": "The RID of the action type to apply in the format ri.actions.main.action-type.{UUID}."
     },
     "ontologyBranchRid": {
      "description": "The RID of the ontology branch to apply the action against in the format ri.ontology.main.branch.{UUID}.If not provided, the action will be applied on main.If an ontology branch RID is provided, the action will fail if the referenced object types have not been indexed on the branchand edits will not be applied to the main branch.",
      "anyOf": [
       {
        "type": "string"
       },
       {
        "type": "null"
       }
      ]
     },
     "parameters": {
      "type": "array",
      "items": {
       "type": "object",
       "properties": {
        "parameterId": {
         "type": "string",
         "description": "The ID of the action parameter."
        },
        "value": {
         "anyOf": [
          {
           "type": "object",
           "properties": {
            "type": {
             "type": "string",
             "const": "staticValue"
            },
            "staticValue": {
             "anyOf": [
              {
               "type": "object",
               "properties": {
                "baseType": {
                 "type": "string",
                 "enum": [
                  "string",
                  "integer",
                  "double",
                  "long",
                  "boolean",
                  "date",
                  "timestamp",
                  "markingId",
                  "attachment"
                 ],
                 "description": "The type of the static value. Specify object and object arrays using the object primary key value."
                },
                "value": {
                 "description": "The static value.",
                 "anyOf": [
                  {
                   "type": "string"
                  },
                  {
                   "type": "number"
                  },
                  {
                   "type": "boolean"
                  },
                  {
                   "type": "null"
                  }
                 ]
                }
               },
               "required": [
                "baseType",
                "value"
               ],
               "additionalProperties": false
              },
              {
               "type": "object",
               "properties": {
                "baseType": {
                 "type": "string",
                 "enum": [
                  "string",
                  "integer",
                  "double",
                  "long",
                  "boolean",
                  "date",
                  "timestamp",
                  "markingId",
                  "attachment"
                 ],
                 "description": "The type of the static value. Specify object and object arrays using the object primary key value."
                },
                "value": {
                 "description": "The array of static value for the parameter with isArray true.",
                 "anyOf": [
                  {
                   "type": "array",
                   "items": {
                    "type": "string"
                   }
                  },
                  {
                   "type": "array",
                   "items": {
                    "type": "number"
                   }
                  },
                  {
                   "type": "array",
                   "items": {
                    "type": "boolean"
                   }
                  },
                  {
                   "type": "null"
                  }
                 ]
                }
               },
               "required": [
                "baseType",
                "value"
               ],
               "additionalProperties": false
              },
              {
               "type": "object",
               "properties": {
                "baseType": {
                 "type": "string",
                 "const": "object"
                },
                "value": {
                 "description": "The primary key value of the object.",
                 "anyOf": [
                  {
                   "type": "string"
                  },
                  {
                   "type": "number"
                  },
                  {
                   "type": "boolean"
                  },
                  {
                   "type": "null"
                  }
                 ]
                }
               },
               "required": [
                "baseType",
                "value"
               ],
               "additionalProperties": false
              },
              {
               "type": "object",
               "properties": {
                "baseType": {
                 "type": "string",
                 "const": "object"
                },
                "value": {
                 "description": "The array of primary key values of the objects for the object parameter with isArray true.",
                 "anyOf": [
                  {
                   "type": "array",
                   "items": {
                    "type": "string"
                   }
                  },
                  {
                   "type": "array",
                   "items": {
                    "type": "number"
                   }
                  },
                  {
                   "type": "array",
                   "items": {
                    "type": "boolean"
                   }
                  },
                  {
                   "type": "null"
                  }
                 ]
                }
               },
               "required": [
                "baseType",
                "value"
               ],
               "additionalProperties": false
              }
             ],
             "description": "The static value to set for the action parameter."
            }
           },
           "required": [
            "type",
            "staticValue"
           ],
           "additionalProperties": false
          },
          {
           "type": "object",
           "properties": {
            "type": {
             "type": "string",
             "const": "aiFdeSessionId",
             "description": "Use the current AI FDE chat session ID as the string value for this parameter."
            }
           },
           "required": [
            "type"
           ],
           "additionalProperties": false
          },
          {
           "type": "object",
           "properties": {
            "type": {
             "type": "string",
             "const": "objectSet"
            },
            "objectSet": {
             "$ref": "#/$defs/__schema0"
            }
           },
           "required": [
            "type",
            "objectSet"
           ],
           "additionalProperties": false
          }
         ],
         "description": "How to populate the action parameter. Use objectSet for object set parameters, defining the set of objects inline; an array of object primary keys is not a valid object set value. Use staticValue for every other parameter type, including single object and object list parameters."
        }
       },
       "required": [
        "parameterId",
        "value"
       ],
       "additionalProperties": false
      },
      "description": "The parameters to set explicitly. Any omitted parameter is prefilled automatically with its configured default value if one exists, otherwise with explicit null."
     }
    },
    "required": [
     "actionTypeRid",
     "parameters",
     "ontologyBranchRid"
    ],
    "additionalProperties": false,
    "$defs": {
     "__schema0": {
      "description": "Represents a collection of Ontology objects (Object Set), to be used as function inputs, that can be composed through filtering, relationship traversal, and set operations",
      "anyOf": [
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "base"
         },
         "base": {
          "type": "object",
          "properties": {
           "objectTypeId": {
            "type": "string",
            "description": "The unique object type ID for the object type. Note: this is not the API name, display name nor the RID."
           }
          },
          "required": [
           "objectTypeId"
          ],
          "additionalProperties": false,
          "description": "A base object set containing all objects of a specific object type"
         }
        },
        "required": [
         "type",
         "base"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "filtered"
         },
         "filtered": {
          "description": "An object set filtered by specific property conditions",
          "type": "object",
          "properties": {
           "objectSet": {
            "$ref": "#/$defs/__schema0"
           },
           "filter": {
            "$ref": "#/$defs/__schema1"
           }
          },
          "additionalProperties": false,
          "required": [
           "objectSet",
           "filter"
          ]
         }
        },
        "required": [
         "type",
         "filtered"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "searchAround"
         },
         "searchAround": {
          "description": "An object set created by traversing relationships from another object set",
          "type": "object",
          "properties": {
           "objectSet": {
            "$ref": "#/$defs/__schema0"
           },
           "relationId": {
            "type": "string"
           },
           "relationSide": {
            "type": "string",
            "enum": [
             "TARGET",
             "SOURCE",
             "EITHER"
            ]
           }
          },
          "required": [
           "relationId",
           "relationSide",
           "objectSet"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "searchAround"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "unioned"
         },
         "unioned": {
          "description": "An object set combining multiple object sets using union (OR)",
          "type": "object",
          "properties": {
           "objectSets": {
            "type": "array",
            "items": {
             "$ref": "#/$defs/__schema0"
            }
           }
          },
          "required": [
           "objectSets"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "unioned"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "intersected"
         },
         "intersected": {
          "description": "An object set containing only objects present in all provided sets (AND)",
          "type": "object",
          "properties": {
           "objectSets": {
            "type": "array",
            "items": {
             "$ref": "#/$defs/__schema0"
            }
           }
          },
          "required": [
           "objectSets"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "intersected"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "subtracted"
         },
         "subtracted": {
          "description": "An object set removing objects from the first set that appear in subsequent sets",
          "type": "object",
          "properties": {
           "objectSets": {
            "type": "array",
            "items": {
             "$ref": "#/$defs/__schema0"
            }
           }
          },
          "required": [
           "objectSets"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "subtracted"
        ],
        "additionalProperties": false
       }
      ]
     },
     "__schema1": {
      "anyOf": [
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "and"
         },
         "and": {
          "type": "object",
          "properties": {
           "filters": {
            "type": "array",
            "items": {
             "$ref": "#/$defs/__schema1"
            }
           }
          },
          "required": [
           "filters"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "and"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "or"
         },
         "or": {
          "type": "object",
          "properties": {
           "filters": {
            "type": "array",
            "items": {
             "$ref": "#/$defs/__schema1"
            }
           }
          },
          "required": [
           "filters"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "or"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "not"
         },
         "not": {
          "type": "object",
          "properties": {
           "filter": {
            "$ref": "#/$defs/__schema1"
           }
          },
          "additionalProperties": false,
          "required": [
           "filter"
          ]
         }
        },
        "required": [
         "type",
         "not"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "hasProperty"
         },
         "hasProperty": {
          "type": "object",
          "properties": {
           "propertyIdentifier": {
            "anyOf": [
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyId"
               },
               "propertyId": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyId"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyApiName"
               },
               "propertyApiName": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyApiName"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "titleProperty"
               },
               "titleProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "titleProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "primaryKeyProperty"
               },
               "primaryKeyProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "primaryKeyProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "structFieldSelector"
               },
               "structFieldSelector": {
                "type": "object",
                "properties": {
                 "structPropertyIdentifier": {
                  "type": "object",
                  "properties": {
                   "apiName": {
                    "type": "string"
                   },
                   "type": {
                    "type": "string",
                    "const": "apiName"
                   }
                  },
                  "required": [
                   "apiName",
                   "type"
                  ],
                  "additionalProperties": false
                 },
                 "structPropertyField": {
                  "type": "object",
                  "properties": {
                   "structPropertyFieldIdentifier": {
                    "type": "object",
                    "properties": {
                     "apiName": {
                      "type": "string"
                     },
                     "type": {
                      "type": "string",
                      "const": "apiName"
                     }
                    },
                    "required": [
                     "apiName",
                     "type"
                    ],
                    "additionalProperties": false
                   }
                  },
                  "required": [
                   "structPropertyFieldIdentifier"
                  ],
                  "additionalProperties": false
                 }
                },
                "required": [
                 "structPropertyIdentifier",
                 "structPropertyField"
                ],
                "additionalProperties": false
               }
              },
              "required": [
               "type",
               "structFieldSelector"
              ],
              "additionalProperties": false
             }
            ]
           }
          },
          "required": [
           "propertyIdentifier"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "hasProperty"
        ],
        "additionalProperties": false,
        "description": "Filters for objects where the property has a non-null value"
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "range"
         },
         "range": {
          "type": "object",
          "properties": {
           "lt": {
            "anyOf": [
             {
              "anyOf": [
               {
                "type": "string"
               },
               {
                "type": "number"
               },
               {
                "type": "boolean"
               },
               {
                "type": "array",
                "items": {
                 "anyOf": [
                  {
                   "type": "string"
                  },
                  {
                   "type": "number"
                  },
                  {
                   "type": "boolean"
                  }
                 ]
                }
               }
              ]
             },
             {
              "type": "null"
             }
            ]
           },
           "lte": {
            "anyOf": [
             {
              "anyOf": [
               {
                "type": "string"
               },
               {
                "type": "number"
               },
               {
                "type": "boolean"
               },
               {
                "type": "array",
                "items": {
                 "anyOf": [
                  {
                   "type": "string"
                  },
                  {
                   "type": "number"
                  },
                  {
                   "type": "boolean"
                  }
                 ]
                }
               }
              ]
             },
             {
              "type": "null"
             }
            ]
           },
           "gt": {
            "anyOf": [
             {
              "anyOf": [
               {
                "type": "string"
               },
               {
                "type": "number"
               },
               {
                "type": "boolean"
               },
               {
                "type": "array",
                "items": {
                 "anyOf": [
                  {
                   "type": "string"
                  },
                  {
                   "type": "number"
                  },
                  {
                   "type": "boolean"
                  }
                 ]
                }
               }
              ]
             },
             {
              "type": "null"
             }
            ]
           },
           "gte": {
            "anyOf": [
             {
              "anyOf": [
               {
                "type": "string"
               },
               {
                "type": "number"
               },
               {
                "type": "boolean"
               },
               {
                "type": "array",
                "items": {
                 "anyOf": [
                  {
                   "type": "string"
                  },
                  {
                   "type": "number"
                  },
                  {
                   "type": "boolean"
                  }
                 ]
                }
               }
              ]
             },
             {
              "type": "null"
             }
            ]
           },
           "propertyIdentifier": {
            "anyOf": [
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyId"
               },
               "propertyId": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyId"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyApiName"
               },
               "propertyApiName": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyApiName"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "titleProperty"
               },
               "titleProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "titleProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "primaryKeyProperty"
               },
               "primaryKeyProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "primaryKeyProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "structFieldSelector"
               },
               "structFieldSelector": {
                "type": "object",
                "properties": {
                 "structPropertyIdentifier": {
                  "type": "object",
                  "properties": {
                   "apiName": {
                    "type": "string"
                   },
                   "type": {
                    "type": "string",
                    "const": "apiName"
                   }
                  },
                  "required": [
                   "apiName",
                   "type"
                  ],
                  "additionalProperties": false
                 },
                 "structPropertyField": {
                  "type": "object",
                  "properties": {
                   "structPropertyFieldIdentifier": {
                    "type": "object",
                    "properties": {
                     "apiName": {
                      "type": "string"
                     },
                     "type": {
                      "type": "string",
                      "const": "apiName"
                     }
                    },
                    "required": [
                     "apiName",
                     "type"
                    ],
                    "additionalProperties": false
                   }
                  },
                  "required": [
                   "structPropertyFieldIdentifier"
                  ],
                  "additionalProperties": false
                 }
                },
                "required": [
                 "structPropertyIdentifier",
                 "structPropertyField"
                ],
                "additionalProperties": false
               }
              },
              "required": [
               "type",
               "structFieldSelector"
              ],
              "additionalProperties": false
             }
            ]
           }
          },
          "required": [
           "propertyIdentifier",
           "lt",
           "lte",
           "gt",
           "gte"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "range"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "terms"
         },
         "terms": {
          "type": "object",
          "properties": {
           "terms": {
            "type": "array",
            "items": {
             "type": "string"
            }
           },
           "propertyIdentifier": {
            "anyOf": [
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyId"
               },
               "propertyId": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyId"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyApiName"
               },
               "propertyApiName": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyApiName"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "titleProperty"
               },
               "titleProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "titleProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "primaryKeyProperty"
               },
               "primaryKeyProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "primaryKeyProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "structFieldSelector"
               },
               "structFieldSelector": {
                "type": "object",
                "properties": {
                 "structPropertyIdentifier": {
                  "type": "object",
                  "properties": {
                   "apiName": {
                    "type": "string"
                   },
                   "type": {
                    "type": "string",
                    "const": "apiName"
                   }
                  },
                  "required": [
                   "apiName",
                   "type"
                  ],
                  "additionalProperties": false
                 },
                 "structPropertyField": {
                  "type": "object",
                  "properties": {
                   "structPropertyFieldIdentifier": {
                    "type": "object",
                    "properties": {
                     "apiName": {
                      "type": "string"
                     },
                     "type": {
                      "type": "string",
                      "const": "apiName"
                     }
                    },
                    "required": [
                     "apiName",
                     "type"
                    ],
                    "additionalProperties": false
                   }
                  },
                  "required": [
                   "structPropertyFieldIdentifier"
                  ],
                  "additionalProperties": false
                 }
                },
                "required": [
                 "structPropertyIdentifier",
                 "structPropertyField"
                ],
                "additionalProperties": false
               }
              },
              "required": [
               "type",
               "structFieldSelector"
              ],
              "additionalProperties": false
             }
            ]
           }
          },
          "required": [
           "terms",
           "propertyIdentifier"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "terms"
        ],
        "additionalProperties": false,
        "description": "Matches objects where the tokenized property matches any of the provided terms. Does not analyze the query string. For example, a property \"The Quick Brown Fox\" produces tokens [\"the\", \"quick\", \"brown\", \"fox\"] and would match a term \"brown\" but not \"Brown\" or \"Brown Fox\". Use exact match for case-sensitive matching."
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "exactMatch"
         },
         "exactMatch": {
          "type": "object",
          "properties": {
           "terms": {
            "type": "array",
            "items": {
             "type": "string"
            }
           },
           "propertyIdentifier": {
            "anyOf": [
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyId"
               },
               "propertyId": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyId"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyApiName"
               },
               "propertyApiName": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyApiName"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "titleProperty"
               },
               "titleProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "titleProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "primaryKeyProperty"
               },
               "primaryKeyProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "primaryKeyProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "structFieldSelector"
               },
               "structFieldSelector": {
                "type": "object",
                "properties": {
                 "structPropertyIdentifier": {
                  "type": "object",
                  "properties": {
                   "apiName": {
                    "type": "string"
                   },
                   "type": {
                    "type": "string",
                    "const": "apiName"
                   }
                  },
                  "required": [
                   "apiName",
                   "type"
                  ],
                  "additionalProperties": false
                 },
                 "structPropertyField": {
                  "type": "object",
                  "properties": {
                   "structPropertyFieldIdentifier": {
                    "type": "object",
                    "properties": {
                     "apiName": {
                      "type": "string"
                     },
                     "type": {
                      "type": "string",
                      "const": "apiName"
                     }
                    },
                    "required": [
                     "apiName",
                     "type"
                    ],
                    "additionalProperties": false
                   }
                  },
                  "required": [
                   "structPropertyFieldIdentifier"
                  ],
                  "additionalProperties": false
                 }
                },
                "required": [
                 "structPropertyIdentifier",
                 "structPropertyField"
                ],
                "additionalProperties": false
               }
              },
              "required": [
               "type",
               "structFieldSelector"
              ],
              "additionalProperties": false
             }
            ]
           }
          },
          "required": [
           "terms",
           "propertyIdentifier"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "exactMatch"
        ],
        "additionalProperties": false,
        "description": "Matches objects where the property value exactly matches one of the provided terms (case-sensitive). Use this for precise matching of property values."
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "wildcard"
         },
         "wildcard": {
          "type": "object",
          "properties": {
           "term": {
            "type": "string"
           },
           "propertyIdentifier": {
            "anyOf": [
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyId"
               },
               "propertyId": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyId"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyApiName"
               },
               "propertyApiName": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyApiName"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "titleProperty"
               },
               "titleProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "titleProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "primaryKeyProperty"
               },
               "primaryKeyProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "primaryKeyProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "structFieldSelector"
               },
               "structFieldSelector": {
                "type": "object",
                "properties": {
                 "structPropertyIdentifier": {
                  "type": "object",
                  "properties": {
                   "apiName": {
                    "type": "string"
                   },
                   "type": {
                    "type": "string",
                    "const": "apiName"
                   }
                  },
                  "required": [
                   "apiName",
                   "type"
                  ],
                  "additionalProperties": false
                 },
                 "structPropertyField": {
                  "type": "object",
                  "properties": {
                   "structPropertyFieldIdentifier": {
                    "type": "object",
                    "properties": {
                     "apiName": {
                      "type": "string"
                     },
                     "type": {
                      "type": "string",
                      "const": "apiName"
                     }
                    },
                    "required": [
                     "apiName",
                     "type"
                    ],
                    "additionalProperties": false
                   }
                  },
                  "required": [
                   "structPropertyFieldIdentifier"
                  ],
                  "additionalProperties": false
                 }
                },
                "required": [
                 "structPropertyIdentifier",
                 "structPropertyField"
                ],
                "additionalProperties": false
               }
              },
              "required": [
               "type",
               "structFieldSelector"
              ],
              "additionalProperties": false
             }
            ]
           }
          },
          "required": [
           "term",
           "propertyIdentifier"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "wildcard"
        ],
        "additionalProperties": false,
        "description": "Matches objects where the property value matches the wildcard pattern. Use * to match any characters and ? to match a single character. For example, \"qu?ck bro*\" would match \"quick brown\"."
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "relativeDateRange"
         },
         "relativeDateRange": {
          "type": "object",
          "properties": {
           "sinceRelativePointInTime": {
            "anyOf": [
             {
              "type": "object",
              "properties": {
               "value": {
                "type": "integer",
                "minimum": -9007199254740991,
                "maximum": 9007199254740991
               },
               "timeUnit": {
                "type": "string",
                "enum": [
                 "MONTH",
                 "YEAR",
                 "WEEK",
                 "DAY"
                ]
               }
              },
              "required": [
               "value",
               "timeUnit"
              ],
              "additionalProperties": false
             },
             {
              "type": "null"
             }
            ]
           },
           "untilRelativePointInTime": {
            "anyOf": [
             {
              "type": "object",
              "properties": {
               "value": {
                "type": "integer",
                "minimum": -9007199254740991,
                "maximum": 9007199254740991
               },
               "timeUnit": {
                "type": "string",
                "enum": [
                 "MONTH",
                 "YEAR",
                 "WEEK",
                 "DAY"
                ]
               }
              },
              "required": [
               "value",
               "timeUnit"
              ],
              "additionalProperties": false
             },
             {
              "type": "null"
             }
            ]
           },
           "timeZoneId": {
            "type": "string",
            "description": "An identifier of a time zone, e.g. \"Europe/London\" as defined by the Time Zone Database"
           },
           "propertyIdentifier": {
            "anyOf": [
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyId"
               },
               "propertyId": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyId"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyApiName"
               },
               "propertyApiName": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyApiName"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "titleProperty"
               },
               "titleProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "titleProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "primaryKeyProperty"
               },
               "primaryKeyProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "primaryKeyProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "structFieldSelector"
               },
               "structFieldSelector": {
                "type": "object",
                "properties": {
                 "structPropertyIdentifier": {
                  "type": "object",
                  "properties": {
                   "apiName": {
                    "type": "string"
                   },
                   "type": {
                    "type": "string",
                    "const": "apiName"
                   }
                  },
                  "required": [
                   "apiName",
                   "type"
                  ],
                  "additionalProperties": false
                 },
                 "structPropertyField": {
                  "type": "object",
                  "properties": {
                   "structPropertyFieldIdentifier": {
                    "type": "object",
                    "properties": {
                     "apiName": {
                      "type": "string"
                     },
                     "type": {
                      "type": "string",
                      "const": "apiName"
                     }
                    },
                    "required": [
                     "apiName",
                     "type"
                    ],
                    "additionalProperties": false
                   }
                  },
                  "required": [
                   "structPropertyFieldIdentifier"
                  ],
                  "additionalProperties": false
                 }
                },
                "required": [
                 "structPropertyIdentifier",
                 "structPropertyField"
                ],
                "additionalProperties": false
               }
              },
              "required": [
               "type",
               "structFieldSelector"
              ],
              "additionalProperties": false
             }
            ]
           }
          },
          "required": [
           "timeZoneId",
           "propertyIdentifier",
           "sinceRelativePointInTime",
           "untilRelativePointInTime"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "relativeDateRange"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "relativeTimeRange"
         },
         "relativeTimeRange": {
          "type": "object",
          "properties": {
           "sinceRelativeMillis": {
            "anyOf": [
             {
              "type": "integer",
              "minimum": -9007199254740991,
              "maximum": 9007199254740991
             },
             {
              "type": "null"
             }
            ]
           },
           "untilRelativeMillis": {
            "anyOf": [
             {
              "type": "integer",
              "minimum": -9007199254740991,
              "maximum": 9007199254740991
             },
             {
              "type": "null"
             }
            ]
           },
           "propertyIdentifier": {
            "anyOf": [
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyId"
               },
               "propertyId": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyId"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "propertyApiName"
               },
               "propertyApiName": {
                "type": "string"
               }
              },
              "required": [
               "type",
               "propertyApiName"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "titleProperty"
               },
               "titleProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "titleProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "primaryKeyProperty"
               },
               "primaryKeyProperty": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
                "required": []
               }
              },
              "required": [
               "type",
               "primaryKeyProperty"
              ],
              "additionalProperties": false
             },
             {
              "type": "object",
              "properties": {
               "type": {
                "type": "string",
                "const": "structFieldSelector"
               },
               "structFieldSelector": {
                "type": "object",
                "properties": {
                 "structPropertyIdentifier": {
                  "type": "object",
                  "properties": {
                   "apiName": {
                    "type": "string"
                   },
                   "type": {
                    "type": "string",
                    "const": "apiName"
                   }
                  },
                  "required": [
                   "apiName",
                   "type"
                  ],
                  "additionalProperties": false
                 },
                 "structPropertyField": {
                  "type": "object",
                  "properties": {
                   "structPropertyFieldIdentifier": {
                    "type": "object",
                    "properties": {
                     "apiName": {
                      "type": "string"
                     },
                     "type": {
                      "type": "string",
                      "const": "apiName"
                     }
                    },
                    "required": [
                     "apiName",
                     "type"
                    ],
                    "additionalProperties": false
                   }
                  },
                  "required": [
                   "structPropertyFieldIdentifier"
                  ],
                  "additionalProperties": false
                 }
                },
                "required": [
                 "structPropertyIdentifier",
                 "structPropertyField"
                ],
                "additionalProperties": false
               }
              },
              "required": [
               "type",
               "structFieldSelector"
              ],
              "additionalProperties": false
             }
            ]
           }
          },
          "required": [
           "propertyIdentifier",
           "sinceRelativeMillis",
           "untilRelativeMillis"
          ],
          "additionalProperties": false
         }
        },
        "required": [
         "type",
         "relativeTimeRange"
        ],
        "additionalProperties": false
       }
      ]
     }
    }
   },
   "strict": false
  },
  "type": "function"
 },
 "request_clarification_from_user": {
  "function": {
   "name": "request_clarification_from_user",
   "description": "Request clarification from the user by asking a set of requests for missing resources, multiple choice questions, and/or free text questions. Use this tool when the task is ambiguous or information is missing.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "questions": {
      "type": "array",
      "items": {
       "anyOf": [
        {
         "type": "object",
         "properties": {
          "reason": {
           "type": "string",
           "description": "Explanation provided to the user explaining why you are requesting the resource and how you might use it."
          },
          "resourceType": {
           "anyOf": [
            {
             "type": "string",
             "const": "datasets",
             "description": "A request for a datasets. Provides RID in the form ri.foundry.xxxx.dataset.{UUID} or ri.gps.xxxx.view.{UUID} or ri.tables.xxxx.table.{UUID} or ri.mio.xxxx.media-set.{UUID})."
            },
            {
             "type": "string",
             "const": "models",
             "description": "A request for a models. Provides RID in the form ri.models.xxxx.model.{UUID})."
            },
            {
             "type": "string",
             "const": "repository",
             "description": "A request for a repository. Provides RID in the form ri.stemma.xxxx.repository.{UUID} or ri.widgetregistry.xxxx.widget-set.{UUID})."
            },
            {
             "type": "string",
             "const": "notepad",
             "description": "A request for a notepad. Provides RID in the form ri.notepad.xxxx.notepad.{UUID})."
            },
            {
             "type": "string",
             "const": "notepadTemplate",
             "description": "A request for a notepadTemplate. Provides RID in the form ri.notepad.xxxx.notepad-template.{UUID})."
            },
            {
             "type": "string",
             "const": "aipSkill",
             "description": "A request for a aipSkill. Provides RID in the form ri.aip-agents.xxxx.skill.{UUID})."
            },
            {
             "type": "string",
             "const": "compassFolder",
             "description": "A request for a compassFolder. Provides RID in the form ri.compass.xxxx.folder.{UUID})."
            },
            {
             "type": "string",
             "const": "namespace",
             "description": "A request for a namespace. Provides RID in the form ri.compass.xxxx.folder.{UUID})."
            },
            {
             "type": "string",
             "const": "machineryGraph",
             "description": "A request for a machineryGraph. Provides RID in the form ri.machinery.xxxx.document.{UUID})."
            },
            {
             "type": "string",
             "const": "solutionDesignDiagram",
             "description": "A request for a solutionDesignDiagram. Provides RID in the form ri.solution-design.xxxx.diagram.{UUID})."
            },
            {
             "type": "string",
             "const": "objectType",
             "description": "A request for a objectType. Provides RID in the form ri.ontology.xxxx.object-type.{UUID})."
            },
            {
             "type": "string",
             "const": "actions",
             "description": "A request for a actions. Provides RID in the form ri.actions.xxxx.action-type.{UUID})."
            },
            {
             "type": "string",
             "const": "functions",
             "description": "A request for a functions. Provides RID in the form ri.function-registry.xxxx.function.{UUID})."
            },
            {
             "type": "string",
             "const": "logicFunction",
             "description": "A request for a logicFunction. Provides RID in the form ri.eddie.xxxx.logic.{UUID})."
            },
            {
             "type": "string",
             "const": "pipelineBuilder",
             "description": "A request for a pipelineBuilder. Provides RID in the form ri.eddie.xxxx.pipeline.{UUID})."
            },
            {
             "type": "string",
             "const": "workflowBuilder",
             "description": "A request for a workflowBuilder. Provides RID in the form ri.workflow-builder.xxxx.edit.{UUID})."
            },
            {
             "type": "string",
             "const": "workshopModule",
             "description": "A request for a workshopModule. Provides RID in the form ri.workshop.xxxx.module.{UUID})."
            },
            {
             "type": "string",
             "const": "slateDocument",
             "description": "A request for a slateDocument. Provides RID in the form ri.slate.xxxx.document.{UUID})."
            },
            {
             "type": "string",
             "const": "contourAnalysis",
             "description": "A request for a contourAnalysis. Provides RID in the form ri.contour.xxxx.analysis.{UUID})."
            },
            {
             "type": "string",
             "const": "automate",
             "description": "A request for a automate. Provides RID in the form ri.object-sentinel.xxxx.monitor.{UUID})."
            },
            {
             "type": "string",
             "const": "interfaceType",
             "description": "A request for a interfaceType. Provides RID in the form ri.ontology.xxxx.interface.{UUID})."
            },
            {
             "type": "string",
             "const": "languageModelFunction",
             "description": "A request for a languageModelFunction. Provides RID in the form ri.language-model-service.xxxx.language-model.{UUID})."
            },
            {
             "type": "string",
             "const": "foundryBranch",
             "description": "A request for a foundryBranch. Provides RID in the form ri.branch.xxxx.branch.{UUID} or ri.ontology.xxxx.branch.{UUID})."
            },
            {
             "type": "string",
             "const": "ontology",
             "description": "A request for a ontology. Provides RID in the form ri.ontology.xxxx.ontology.{UUID})."
            },
            {
             "type": "string",
             "const": "cipherChannel",
             "description": "A request for a cipherChannel. Provides RID in the form ri.bellaso.xxxx.cipher-channel.{UUID})."
            },
            {
             "type": "string",
             "const": "cipherLicense",
             "description": "A request for a cipherLicense. Provides RID in the form ri.bellaso.xxxx.cipher-license.{UUID})."
            },
            {
             "type": "string",
             "const": "evaluationSuite",
             "description": "A request for a evaluationSuite. Provides RID in the form ri.evals.xxxx.evaluation-suite.{UUID})."
            },
            {
             "type": "string",
             "const": "object",
             "description": "A request for a object. Provides RID in the form ri.phonograph2-objects.xxxx.object.{UUID})."
            },
            {
             "type": "string",
             "const": "source",
             "description": "A request for a source. Provides RID in the form ri.magritte.xxxx.source.{UUID})."
            },
            {
             "type": "string",
             "const": "dataConnectionAgent",
             "description": "A request for a dataConnectionAgent. Provides RID in the form ri.magritte.xxxx.agent.{UUID})."
            },
            {
             "type": "string",
             "const": "egressPolicy",
             "description": "A request for a egressPolicy. Provides RID in the form ri.resource-policy-manager.xxxx.network-egress-policy.{UUID})."
            },
            {
             "type": "string",
             "const": "objectSet",
             "description": "A request for a objectSet. Provides RID in the form ri.object-set.xxxx.object-set.{UUID} or ri.object-set.xxxx.versioned-object-set.{UUID} or ri.object-set.xxxx.temporary-object-set.{UUID})."
            },
            {
             "type": "string",
             "const": "timeSeriesSyncs",
             "description": "A request for a timeSeriesSyncs. Provides RID in the form ri.time-series-catalog.xxxx.sync.{UUID})."
            },
            {
             "type": "string",
             "const": "sqlWorksheet",
             "description": "A request for a sqlWorksheet. Provides RID in the form ri.foundry-sql-server.xxxx.worksheet.{UUID})."
            }
           ],
           "description": "The type of resource to request from the user. Use this option if you require a resource in order to complete a task but it is not available (e.g., need to create a code repository but do not have a folder to create it in)."
          }
         },
         "required": [
          "reason",
          "resourceType"
         ],
         "additionalProperties": false
        },
        {
         "type": "object",
         "properties": {
          "multipleChoiceQuestion": {
           "type": "string",
           "description": "The question that the user can help clarify."
          },
          "allowMultiSelect": {
           "type": "boolean",
           "description": "When true, the user can select multiple choices.."
          },
          "choices": {
           "minItems": 2,
           "type": "array",
           "items": {
            "type": "string"
           },
           "description": "The list of choices the user can select from. Do not specify a free text \"other\" option, as this will always be automatically included."
          }
         },
         "required": [
          "multipleChoiceQuestion",
          "allowMultiSelect",
          "choices"
         ],
         "additionalProperties": false
        },
        {
         "type": "object",
         "properties": {
          "freeTextQuestion": {
           "type": "string",
           "description": "A question that the user can answer with free text. Use only if the question cannot be answered with a multiple choice question and you are not requesting a specific resource.. Never use a freeTextQuestion to ask the user for a RID or other identifiers, use resourceType instead."
          }
         },
         "required": [
          "freeTextQuestion"
         ],
         "additionalProperties": false
        }
       ],
       "description": "A clarification request. Prefer requesting resourceType or multiple choice questions over free text responses where possible."
      },
      "description": "A list of questions to ask the user to clarify the task. You can use any question type for the questions, including repeating question types. Avoid asking more than 3 questions at a time."
     }
    },
    "required": [
     "questions"
    ],
    "additionalProperties": false
   },
   "strict": true
  },
  "type": "function"
 },
 "change_mode": {
  "function": {
   "name": "change_mode",
   "description": "Change the current mode configuration. This will grant access to different tools and documentation. Use this tool to change the task you are performing, e.g. transitioning from creating object types to writing functions that use the object types that were created.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "modeConfig": {
      "anyOf": [
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "dataIntegration",
          "description": "Configure tools and documentation for creating or modifying data transformation pipelines in Foundry using Python transforms or Pipeline Builder. Only use when the task is purely about data transformation with no modeling goal. Prefer codeWorkspaces for codeEditingType unless authoring is specifically requested by the user."
         },
         "transformsType": {
          "anyOf": [
           {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "pythonTransforms",
              "description": "Configure for Python-based data transformation pipelines."
             },
             "codeEditingType": {
              "type": "string",
              "enum": [
               "codeWorkspaces",
               "authoring"
              ],
              "description": "Choose the code editing environment. Use Code Workspaces unless legacy authoring is specifically requested by the user."
             }
            },
            "required": [
             "type",
             "codeEditingType"
            ]
           },
           {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "pipelineBuilder",
              "description": "Configure for Pipeline Builder-based no-code data transformation pipelines."
             }
            },
            "required": [
             "type"
            ]
           }
          ]
         },
         "branchingType": {
          "type": "string",
          "enum": [
           "foundryBranching",
           "localBranching"
          ],
          "description": "Choose the branching strategy. Use Global Branching in most cases, since it allows changes that span multiple applications or require cross-application coordination; use local branching if you are certain changes are scoped to a single code repository."
         },
         "objectTypeEditing": {
          "type": "boolean",
          "description": "Include object type and link type editing tools. Enable if the task requires creating or modifying object type definitions or link types."
         },
         "unstructuredData": {
          "description": "Tools and documentation for unstructured data.",
          "type": "object",
          "properties": {
           "enabled": {
            "type": "boolean",
            "description": "Include unstructured data documentation and tools. Enable if the task involves working with media sets or datasets containing raw files."
           },
           "includeDocumentExtraction": {
            "description": "Add tools and instructions for testing a PDF extraction method and applying it to a media set in a transform. Enable this for pipelines that extract text, tables, or layout from PDFs. This setting only applies when unstructured data is enabled.",
            "anyOf": [
             {
              "type": "boolean"
             },
             {
              "type": "null"
             }
            ]
           }
          },
          "required": [
           "enabled"
          ]
         },
         "externalTransforms": {
          "type": "boolean",
          "description": "Include external transforms documentation. Enable if the task involves writing transforms that read from or interact with external systems."
         },
         "cipher": {
          "description": "Include Cipher data protection tools. Enable if the task involves encrypting or decrypting sensitive data columns.",
          "anyOf": [
           {
            "type": "boolean"
           },
           {
            "type": "null"
           }
          ]
         },
         "schedules": {
          "description": "Include schedule management tools. Enable if the task involves creating, updating, pausing, unpausing, running, or inspecting dataset schedules.",
          "anyOf": [
           {
            "type": "boolean"
           },
           {
            "type": "null"
           }
          ]
         },
         "timeSeriesData": {
          "description": "Include time series catalog tools and documentation. Enable if the task involves creating, updating, running, or inspecting time series syncs for time series datasets or streams.",
          "anyOf": [
           {
            "type": "boolean"
           },
           {
            "type": "null"
           }
          ]
         },
         "useLanguageModels": {
          "description": "Include language model lookup tools and documentation. Enable if the task involves using language models or embeddings in transforms.",
          "anyOf": [
           {
            "type": "boolean"
           },
           {
            "type": "null"
           }
          ]
         }
        },
        "required": [
         "type",
         "transformsType",
         "branchingType",
         "objectTypeEditing",
         "unstructuredData",
         "externalTransforms"
        ],
        "description": "Configure tools and documentation for creating or modifying data transformation pipelines in Foundry using Python transforms or Pipeline Builder. Only use when the task is purely about data transformation with no modeling goal. Prefer codeWorkspaces for codeEditingType unless authoring is specifically requested by the user."
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "dataConnection",
          "description": "Configure tools for creating, managing, and debugging data connection sources, network egress policies, and connectivity to external systems in Foundry."
         }
        },
        "required": [
         "type"
        ],
        "description": "Configure tools for creating, managing, and debugging data connection sources, network egress policies, and connectivity to external systems in Foundry."
       },
       {
        "description": "Configure tools for creating or updating object types, link types, and action types in the ontology.",
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "ontologyEditing",
          "description": "Configure tools for creating or updating object types, link types, and action types in the ontology."
         },
         "includeObjectTypes": {
          "type": "boolean",
          "description": "Include object type and link type editing tools. Enable if the task requires creating or modifying object type definitions or link types."
         },
         "includeActionTypes": {
          "type": "boolean",
          "description": "Include action type editing tools. Enable if the task requires creating or modifying action types."
         },
         "includeInterfaces": {
          "type": "boolean",
          "description": "Include interface editing tools. Enable if the task involves implementing interface types."
         },
         "allowDeletion": {
          "type": "boolean",
          "description": "Include deletion tools for object types, action types, and link types. Only include if the user has requested deletion (e.g., for ontology cleanup)."
         },
         "enableMachinery": {
          "description": "Enable business process modeling tools. Enable if the task involves business process modeling or implementing a multi-step business workflow.",
          "anyOf": [
           {
            "type": "boolean"
           },
           {
            "type": "null"
           }
          ]
         },
         "enableAutomate": {
          "description": "Enable Automate tools. Enable if the task involves creating or managing business automations, which run effects in response to a condition being met, a schedule, or both.",
          "anyOf": [
           {
            "type": "boolean"
           },
           {
            "type": "null"
           }
          ]
         }
        },
        "required": [
         "type",
         "includeObjectTypes",
         "includeActionTypes",
         "includeInterfaces",
         "allowDeletion"
        ]
       },
       {
        "description": "Configure tools and documentation for creating or editing Foundry functions that execute logic on Ontology objects. Function types: AIP Logic (no-code), TypeScript V1 (pro-code), TypeScript V2 (pro-code), Python (pro-code). Use AIP Logic for no-code rule-based tasks.",
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "functionsEditing",
          "description": "Configure tools and documentation for creating or editing Foundry functions that execute logic on Ontology objects. Function types: AIP Logic (no-code), TypeScript V1 (pro-code), TypeScript V2 (pro-code), Python (pro-code). Use AIP Logic for no-code rule-based tasks."
         },
         "functionsType": {
          "type": "object",
          "properties": {
           "selected": {
            "type": "string",
            "enum": [
             "logic",
             "typescriptV1",
             "typescriptV2",
             "python"
            ],
            "description": "Select the functions type based on the user's stated preference and the existing repository (if available)."
           },
           "logic": {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "logic",
              "description": "AIP Logic (no-code). Choose when the task involves rule-based logic or simple transformations without requiring a full programming language."
             }
            },
            "required": [
             "type"
            ]
           },
           "typescriptV1": {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "typescriptV1",
              "description": "TypeScript v1 (pro-code). Choose for existing TypeScript v1 repositories or when the user explicitly requests TypeScript v1."
             }
            },
            "required": [
             "type"
            ]
           },
           "typescriptV2": {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "typescriptV2",
              "description": "TypeScript v2 (pro-code). Choose for new TypeScript functions or when the user explicitly requests TypeScript v2."
             }
            },
            "required": [
             "type"
            ]
           },
           "python": {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "python",
              "description": "Python (pro-code). Choose when the user explicitly requests Python or the task involves data science, ML, or an existing Python Functions repository."
             },
             "documentExtraction": {
              "description": "Add tools and instructions for testing a PDF extraction method and implementing it as a Python function. Enable this when the function must extract text, tables, or layout from PDFs.",
              "anyOf": [
               {
                "type": "boolean"
               },
               {
                "type": "null"
               }
              ]
             }
            },
            "required": [
             "type"
            ]
           }
          },
          "required": [
           "selected",
           "logic",
           "typescriptV1",
           "typescriptV2",
           "python"
          ]
         },
         "externalFunctions": {
          "description": "Include external functions tools and documentation. Enable if the task involves calling external APIs, using webhooks, or importing data connection sources into a functions repository to interact with systems outside Foundry.",
          "anyOf": [
           {
            "type": "boolean"
           },
           {
            "type": "null"
           }
          ]
         },
         "evals": {
          "description": "Include Evals tools. Enable if the task would benefit from creating or running evaluation suites to ensure the implementation meets requirements and behaves as expected.",
          "anyOf": [
           {
            "type": "boolean"
           },
           {
            "type": "null"
           }
          ]
         },
         "enableMachinery": {
          "description": "Enable business process modeling tools. Enable if the task involves business process modeling or implementing a multi-step business workflow.",
          "anyOf": [
           {
            "type": "boolean"
           },
           {
            "type": "null"
           }
          ]
         },
         "ontologyEditFunctions": {
          "type": "boolean",
          "description": "Include ontology edit function tools and documentation. Enable if the task requires creating or editing functions that modify ontology objects through action types."
         },
         "useLanguageModels": {
          "type": "boolean",
          "description": "Include language model tools and documentation. Enable if the task involves using language models or embeddings within functions."
         },
         "allowObjectTypeEdits": {
          "type": "boolean",
          "description": "Include object type editing tools. Enable if you anticipate functions requiring object type definition changes."
         },
         "enableAutomate": {
          "description": "Enable Automate tools. Enable if the task involves creating or managing business automations, which run effects in response to a condition being met, a schedule, or both.",
          "anyOf": [
           {
            "type": "boolean"
           },
           {
            "type": "null"
           }
          ]
         }
        },
        "required": [
         "type",
         "functionsType",
         "ontologyEditFunctions",
         "useLanguageModels",
         "allowObjectTypeEdits"
        ]
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "exploration",
          "description": "Explore and investigate object types, transforms, functions, and datasets in the Foundry platform."
         },
         "enableSearch": {
          "type": "boolean",
          "description": "Include search tools for discovering ontology entities, datasets, functions, global branches, and other resources. Enable if you need to find resources that are not directly related to the resources already available to you."
         }
        },
        "required": [
         "type",
         "enableSearch"
        ],
        "description": "Explore and investigate object types, transforms, functions, and datasets in the Foundry platform."
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "governance",
          "description": "Configure tools and documentation for investigating data governance, permissions, markings, and access control."
         }
        },
        "required": [
         "type"
        ],
        "description": "Configure tools and documentation for investigating data governance, permissions, markings, and access control."
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "applicationBuilding",
          "description": "Configure tools and documentation for building Foundry applications, including Workshop modules, OSDK React apps, custom OSDK widgets, and Gotham artifacts."
         },
         "applicationType": {
          "anyOf": [
           {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "workshop",
              "description": "Build a native Foundry Workshop module (no-code/low-code, not a code repository)."
             }
            },
            "required": [
             "type"
            ]
           },
           {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "osdkApplication",
              "description": "Build a standalone OSDK React application."
             },
             "includeOsdkReactLibraryDocs": {
              "type": "boolean",
              "description": "Include @osdk/react library documentation. Enable if the task involves using React hooks for querying Foundry objects, executing actions, or subscribing to real-time updates."
             },
             "includeOsdkReactComponentsDocs": {
              "type": "boolean",
              "description": "Include @osdk/react-components documentation. Enable if the task involves using pre-built UI components (e.g., ObjectTable) for displaying and interacting with Foundry ontology data."
             },
             "includeBlueprintjsDocs": {
              "type": "boolean",
              "description": "Include BlueprintJS component library documentation. Enable if the task involves building UI with Blueprint components."
             }
            },
            "required": [
             "type",
             "includeOsdkReactLibraryDocs",
             "includeOsdkReactComponentsDocs",
             "includeBlueprintjsDocs"
            ]
           },
           {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "osdkWidgetSet",
              "description": "Build OSDK React widgets that can be embedded in Foundry Workshop."
             },
             "includeOsdkReactLibraryDocs": {
              "type": "boolean",
              "description": "Include @osdk/react library documentation. Enable if the task involves using React hooks for querying Foundry objects, executing actions, or subscribing to real-time updates."
             },
             "includeOsdkReactComponentsDocs": {
              "type": "boolean",
              "description": "Include @osdk/react-components documentation. Enable if the task involves using pre-built UI components (e.g., ObjectTable) for displaying and interacting with Foundry ontology data."
             },
             "includeBlueprintjsDocs": {
              "type": "boolean",
              "description": "Include BlueprintJS component library documentation. Enable if the task involves building UI with Blueprint components."
             }
            },
            "required": [
             "type",
             "includeOsdkReactLibraryDocs",
             "includeOsdkReactComponentsDocs",
             "includeBlueprintjsDocs"
            ]
           }
          ]
         }
        },
        "required": [
         "type",
         "applicationType"
        ],
        "description": "Configure tools and documentation for building Foundry applications, including Workshop modules, OSDK React apps, custom OSDK widgets, and Gotham artifacts."
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "machineLearning",
          "description": "Train, evaluate, deploy, and tune machine learning models in Foundry. Covers classification, regression, time series forecasting, and custom predictive modeling. Run batch or live inference, track experiments, and manage model versions. Supports Model Studio (no-code, paired with Pipeline Builder for feature engineering) and pro-code repositories. Use this mode even if the data needs preprocessing first, as long as the end goal involves model training, evaluation, deployment, or inference."
         },
         "modelingType": {
          "anyOf": [
           {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "modelStudio",
              "description": "Train models with Model Studio and use Pipeline Builder for feature engineering, evaluation transforms, and batch inference. Prefer this for classification, regression, and time series forecasting problems."
             }
            },
            "required": [
             "type"
            ]
           },
           {
            "type": "object",
            "properties": {
             "type": {
              "type": "string",
              "const": "proCode",
              "description": "Train models in code repositories, when required by the user or for other problem types."
             },
             "codeEditingType": {
              "default": "codeWorkspaces",
              "description": "Choose the code editing environment. Use Code Workspaces unless legacy authoring is specifically requested by the user.",
              "type": "string",
              "enum": [
               "codeWorkspaces",
               "authoring"
              ]
             }
            },
            "required": [
             "type"
            ]
           }
          ]
         }
        },
        "required": [
         "type",
         "modelingType"
        ],
        "description": "Train, evaluate, deploy, and tune machine learning models in Foundry. Covers classification, regression, time series forecasting, and custom predictive modeling. Run batch or live inference, track experiments, and manage model versions. Supports Model Studio (no-code, paired with Pipeline Builder for feature engineering) and pro-code repositories. Use this mode even if the data needs preprocessing first, as long as the end goal involves model training, evaluation, deployment, or inference."
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "platformQna",
          "description": "Find information and answer questions about the Foundry platform using tools for searching and loading documentation. It has no other tools: it cannot make changes to Foundry resources, and it cannot read data or logic. When a task requires making changes to Foundry resources, use a mode that can make them instead. When a task requires reading data or logic, use exploration mode."
         }
        },
        "required": [
         "type"
        ],
        "description": "Find information and answer questions about the Foundry platform using tools for searching and loading documentation. It has no other tools: it cannot make changes to Foundry resources, and it cannot read data or logic. When a task requires making changes to Foundry resources, use a mode that can make them instead. When a task requires reading data or logic, use exploration mode."
       }
      ]
     }
    },
    "required": [
     "modeConfig"
    ],
    "additionalProperties": false
   },
   "strict": false
  },
  "type": "function"
 },
 "enable_capabilities": {
  "function": {
   "name": "enable_capabilities",
   "description": "Enable additional capabilities. The listed capabilities will be enabled without affecting your currently active capabilities. Use this to expand your capabilities, e.g. to enable the ability to request clarification from the user.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "capabilities": {
      "type": "array",
      "items": {
       "anyOf": [
        {
         "type": "string",
         "const": "changeMode",
         "description": "Switch operational modes to load different docs and tools."
        },
        {
         "type": "string",
         "const": "requestClarification",
         "description": "Ask the user multiple choice questions, free text questions, or request specific resources."
        },
        {
         "type": "string",
         "const": "loadDocumentation",
         "description": "Load individual documentation pages or documentation bundles."
        },
        {
         "type": "string",
         "const": "manageContext",
         "description": "Add or remove information from context. Do not disable this capability."
        },
        {
         "type": "string",
         "const": "manageCapabilities",
         "description": "Enable or disable specific capabilities. Do not disable this capability."
        },
        {
         "type": "string",
         "const": "notepad",
         "description": "Load, update, and create Notepad documents."
        },
        {
         "type": "string",
         "const": "generatePlan",
         "description": "Adds a generate plan tool to plan changes before executing. Enable this capability if the problem is ambiguous."
        },
        {
         "type": "string",
         "const": "managePlan",
         "description": "Create, write, edit, and read the plan document during planning."
        },
        {
         "type": "string",
         "const": "solutionDesign",
         "description": "Create and modify solution design diagrams."
        },
        {
         "type": "string",
         "const": "workflowLineage",
         "description": "Visualize a set of resources and the connections between them as a graph. Enable this capability to show the user a workflow you built, changed, or explored, or to show a resource's dependencies and dependents."
        },
        {
         "type": "string",
         "const": "executeAction",
         "description": "Execute actions on objects."
        },
        {
         "type": "string",
         "const": "filesystem",
         "description": "Create folders, browse folder contents, update resource metadata, and move resources in the filesystem."
        },
        {
         "type": "string",
         "const": "resourceDocumentation",
         "description": "View and edit resource documentation."
        },
        {
         "type": "string",
         "const": "subagents",
         "description": "Launch sub-agents to perform tasks in parallel."
        },
        {
         "type": "string",
         "const": "manageTodoList",
         "description": "Create and update a todo list to track progress on complex tasks or a plan."
        },
        {
         "type": "string",
         "const": "viewPermissions",
         "description": "View access requirements for resources."
        },
        {
         "type": "string",
         "const": "foundryIssues",
         "description": "Retrieve Foundry Issues and post comments back to them. Comment posting requires human approval."
        },
        {
         "type": "string",
         "const": "loadSkills",
         "description": "Load AIP skills enabled for this session into context."
        },
        {
         "type": "string",
         "const": "editSkills",
         "description": "Inspect, create, and edit AIP skills. Not required for using skills. Only enable if creating and editing skills."
        }
       ]
      },
      "description": "The capabilities to enable."
     }
    },
    "required": [
     "capabilities"
    ],
    "additionalProperties": false
   },
   "strict": false
  },
  "type": "function"
 },
 "disable_capabilities": {
  "function": {
   "name": "disable_capabilities",
   "description": "Disable specific capabilities. Only the listed capabilities will be disabled; all your other capabilities keep their current state.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "capabilities": {
      "type": "array",
      "items": {
       "anyOf": [
        {
         "type": "string",
         "const": "changeMode",
         "description": "Switch operational modes to load different docs and tools."
        },
        {
         "type": "string",
         "const": "requestClarification",
         "description": "Ask the user multiple choice questions, free text questions, or request specific resources."
        },
        {
         "type": "string",
         "const": "loadDocumentation",
         "description": "Load individual documentation pages or documentation bundles."
        },
        {
         "type": "string",
         "const": "manageContext",
         "description": "Add or remove information from context. Do not disable this capability."
        },
        {
         "type": "string",
         "const": "manageCapabilities",
         "description": "Enable or disable specific capabilities. Do not disable this capability."
        },
        {
         "type": "string",
         "const": "notepad",
         "description": "Load, update, and create Notepad documents."
        },
        {
         "type": "string",
         "const": "generatePlan",
         "description": "Adds a generate plan tool to plan changes before executing. Enable this capability if the problem is ambiguous."
        },
        {
         "type": "string",
         "const": "managePlan",
         "description": "Create, write, edit, and read the plan document during planning."
        },
        {
         "type": "string",
         "const": "solutionDesign",
         "description": "Create and modify solution design diagrams."
        },
        {
         "type": "string",
         "const": "workflowLineage",
         "description": "Visualize a set of resources and the connections between them as a graph. Enable this capability to show the user a workflow you built, changed, or explored, or to show a resource's dependencies and dependents."
        },
        {
         "type": "string",
         "const": "executeAction",
         "description": "Execute actions on objects."
        },
        {
         "type": "string",
         "const": "filesystem",
         "description": "Create folders, browse folder contents, update resource metadata, and move resources in the filesystem."
        },
        {
         "type": "string",
         "const": "resourceDocumentation",
         "description": "View and edit resource documentation."
        },
        {
         "type": "string",
         "const": "subagents",
         "description": "Launch sub-agents to perform tasks in parallel."
        },
        {
         "type": "string",
         "const": "manageTodoList",
         "description": "Create and update a todo list to track progress on complex tasks or a plan."
        },
        {
         "type": "string",
         "const": "viewPermissions",
         "description": "View access requirements for resources."
        },
        {
         "type": "string",
         "const": "foundryIssues",
         "description": "Retrieve Foundry Issues and post comments back to them. Comment posting requires human approval."
        },
        {
         "type": "string",
         "const": "loadSkills",
         "description": "Load AIP skills enabled for this session into context."
        },
        {
         "type": "string",
         "const": "editSkills",
         "description": "Inspect, create, and edit AIP skills. Not required for using skills. Only enable if creating and editing skills."
        }
       ]
      },
      "description": "The capabilities to disable."
     }
    },
    "required": [
     "capabilities"
    ],
    "additionalProperties": false
   },
   "strict": false
  },
  "type": "function"
 },
 "manage_context": {
  "function": {
   "name": "manage_context",
   "description": "Manage context window usage by hiding or unhiding context items. Use this tool to hide older, less relevant tool responses when the context window is getting full. Hidden items retain their request metadata but their full response content is removed from context, significantly reducing token usage. Prefer hiding the oldest and least relevant tool responses first.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "contextItemIds": {
      "minItems": 1,
      "type": "array",
      "items": {
       "type": "string"
      },
      "description": "Array of context item IDs to hide or unhide. Use the contextItemId values from the <context-item> metadata tags in the conversation. Do NOT generate or guess IDs."
     },
     "action": {
      "anyOf": [
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "hide",
          "description": "Hide context items, replacing their content with a compact summary. Reduces token usage; the items remain restorable via unhide."
         },
         "assistantSummary": {
          "type": "string",
          "description": "Concise summary of learnings and insights to carry forward \u2014 conclusions drawn, patterns observed, decisions made, facts you'll need to act on. Write as a compact note to yourself that will prevent you from needing to unhide this content again. If the content had no lasting value, write a single sentence explaining why it can be discarded."
         }
        },
        "required": [
         "type",
         "assistantSummary"
        ],
        "additionalProperties": false
       },
       {
        "type": "object",
        "properties": {
         "type": {
          "type": "string",
          "const": "unhide",
          "description": "Restore the full content of previously hidden items."
         }
        },
        "required": [
         "type"
        ],
        "additionalProperties": false
       }
      ]
     }
    },
    "required": [
     "contextItemIds",
     "action"
    ],
    "additionalProperties": false
   },
   "strict": true
  },
  "type": "function"
 },
 "load_skill": {
  "function": {
   "name": "load_skill",
   "description": "Load an AIP skill's full instructions into context by name. Call this when a skill's 'when to use' matches the current task.",
   "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
     "skillName": {
      "type": "string",
      "description": "The name of the AIP skill to load."
     }
    },
    "required": [
     "skillName"
    ],
    "additionalProperties": false
   },
   "strict": true
  },
  "type": "function"
 }
}"""

TOOL_SPECS = json.loads(TOOL_SPECS_JSON)

CAPTURED_INSTRUCTIONS_PREFIX = '- Respond with Markdown\n- Do not attempt to generate links to resources in your responses, always use the markdown instructions provided below to reference resources.\n\n<markdownInstructions>\n\n\nWhen generating markdown, follow these rules:\n- You can use Mermaid for diagrams in your responses, if the user asks for them or if it is necessary to explain your reasoning clearly.\n- Always use the Markdown directive format to render resources that have a RID (e.g., object types, datasets, global branches, etc.). This allows the user to navigate to the resource without explicit URLs.\n    - Only reference resources that have RIDs that you have already seen.\n    - Do not reference resources within mermaid diagrams.\n    - Use the following format to render resources in markdown:\n        - Always close the RID with `]` (square bracket). Never close it with `}` \u2014 `}` only closes the optional attribute block that comes *after* `]`.\n        - Resources (main branch or unbranched resources) - :resource[rid]\n        - Resources (global branch) - :resource[rid]{globalBranchRid="ri.branch..branch.xxxx"}\n        - Resources (Ontology branch) - :resource[rid]{ontologyBranchRid="ri.ontology.main.branch.xxxx"}\n        - Resource (branch name) - :resource[rid]{branchName="branch-name"}\n    - Example: instead of `dataset_name`, use :resource[ri.foundry.main.dataset.1234]{ontologyBranchRid="ri.foundry.main.dataset.5678"}\n- When citing documentation from documentation_search results, use the citation directive format:\n    - Format: :citation[title]{path="path"} or :citation[title]{path="path" section="sectionTitle"}\n    - The title, path, and sectionTitle should come from the document\'s attributes in the search results.\n    - Include the section attribute when the document has a sectionTitle.\n    - Place citations inline at the end of the relevant statement.\n    - Example: :citation[AIP Logic / Getting Started]{path="foundry/aip-logic/overview" section="Getting Started"}\n    - Only cite documents whose paths appeared in documentation_search results.\n\n\n</markdownInstructions>\n\n<selectedMode>{"type":"functionsEditing","functionsType":{"selected":"typescriptV2","logic":{"type":"logic"},"typescriptV1":{"type":"typescriptV1"},"typescriptV2":{"type":"typescriptV2"},"python":{"type":"python","documentExtraction":false}},"externalFunctions":false,"evals":true,"enableMachinery":false,"enableWorkflowBuilders":false,"enableAutomate":false,"ontologyEditFunctions":false,"useLanguageModels":true,"allowObjectTypeEdits":false}</selectedMode>\n\n<instructions>You are responsible for creating and editing typescriptV2 functions in Palantir\'s Foundry platform.\n\nIf the repository includes an AGENTS.md file, treat it as the authoritative source for repository-specific capabilities, SDK patterns, CLI commands, and tooling available at the current branch.\n\n<functionsOverview>\n# Summary: TypeScript v2 Functions in Foundry\n\n## Key Concepts\n\n### 1. Function Structure & Exports\n- Functions are **standalone functions** with `export default` (NOT class methods)\n- **No decorators required** - the function signature defines capabilities\n- Query functions use `export const config = { apiName: "..." }` for API exposure\n- Functions interacting with the Ontology require a `Client` parameter from `@osdk/client`\n\n```typescript\n// Basic function\nimport { Integer } from "@osdk/functions";\n\nfunction add(a: Integer, b: Integer): Integer {\n    return a + b;\n}\nexport default add;\n\n// Query function (exposed via API)\nexport const config = { apiName: "myQueryFunction" };\nexport default function myQuery(): string { return "hello"; }\n```\n\n### 2. Type System Requirements\n- **All parameters must have explicit type annotations**\n- **All functions must specify explicit return types**\n- **Numeric types**: Use `Integer`, `Long`, `Float`, `Double` from `@osdk/functions`\n  - `Long` is an alias for `string` (NOT `number`) to prevent precision loss\n- **Temporal types**: Use `DateISOString`, `TimestampISOString` (ISO string formats)\n- **Object instances**: Use `Osdk.Instance<ObjectType>`\n- **Object sets**: Use `ObjectSet<ObjectType>` from `@osdk/client`\n- **Maps with object keys**: Use `Record<ObjectSpecifier<ObjectType>, V>` and `obj.$objectSpecifier`\n- **Custom types**: Define via `interface` with all fields typed\n\n### 3. Working with Ontology Objects\n- **Requires Client**: Must pass `Client` from `@osdk/client` to access Ontology\n- **Property access**: `employee.firstName` (may be `undefined`)\n- **Loading objects**:\n  - Single: `await client(Employee).fetchOne(primaryKey)`\n  - Page: `await client(Employee).fetchPage()`\n  - Iterate: `for await (const obj of client(Employee).asyncIter()) { }`\n- **Object specifier** (for maps/identification): `obj.$objectSpecifier`\n\n### 4. Object Set Operations\n- **Creating object sets**: `client(ObjectType)` or `client(ObjectType).where({...})`\n- **Filter syntax** uses object notation with `$` operators:\n\n| Operator | Usage | Description |\n|----------|-------|-------------|\n| `$eq` | `{ prop: { $eq: value } }` | Exact match |\n| `$ne` | `{ prop: { $ne: value } }` | Not equal |\n| `$gt`, `$gte` | `{ prop: { $gt: value } }` | Greater than (or equal) |\n| `$lt`, `$lte` | `{ prop: { $lt: value } }` | Less than (or equal) |\n| `$in` | `{ prop: { $in: [v1, v2] } }` | Match any value in array |\n| `$isNull` | `{ prop: { $isNull: true } }` | Null check |\n| `$containsAnyTerm` | `{ prop: { $containsAnyTerm: "word" } }` | Token match |\n| `$containsAllTerms` | `{ prop: { $containsAllTerms: "word1 word2" } }` | All tokens match |\n| `$containsAllTermsInOrder` | `{ prop: { $containsAllTermsInOrder: "phrase" } }` | Phrase match |\n\n```typescript\n// Filtering example\nconst activeEmployees = client(Employee).where({\n    status: { $eq: "active" },\n    age: { $gte: 18, $lte: 65 },\n    department: { $in: ["Engineering", "Product"] }\n});\n```\n\n- **Combining filters**: Use `$and`, `$or`, `$not` at the top level\n```typescript\nclient(Employee).where({\n    $or: [\n        { department: { $eq: "Engineering" } },\n        { yearsExperience: { $gt: 5 } }\n    ]\n});\n```\n\n- **Search Around (Link traversal)**: Use `.pivotTo("linkApiName")`\n```typescript\nconst flights = client(Aircraft).where({ tailNumber: { $eq: "N12345" } });\nconst passengers = flights.pivotTo("passengers");\n```\n\n- **Aggregations**: Use `.aggregate({ $select: {...} })`\n```typescript\nconst result = await client(Employee).aggregate({\n    $select: {\n        $count: "unordered",\n        "salary:sum": "unordered",\n        "salary:avg": "unordered"\n    }\n});\n// Access: result.$count, result.salary.sum, result.salary.avg\n```\n\n- **Grouping**: Use `$groupBy` in aggregations\n```typescript\nconst byDept = await client(Employee).aggregate({\n    $select: { $count: "unordered" },\n    $groupBy: { department: "exact" }\n});\n```\n\n- **Ordering & Limiting**: Chain `.orderBy()` with `.take()`\n```typescript\nconst topEmployees = await client(Employee)\n    .orderBy({ salary: "desc" })\n    .take(10);\n```\n\n- **Set operations**: Use object set methods\n  - `.union(otherSet)`\n  - `.intersect(otherSet)`\n  - `.subtract(otherSet)`\n\n- **Limits**: Max 10,000 objects loadable, max 10,000 aggregation buckets\n\n### 5. Ontology Edits\n- **Must explicitly return edits** - function returns `OntologyEdit[]`\n- **Create edit batch**: `const batch = createEditBatch<OntologyEdit>(client)`\n- **Declare edit types** using union of `Edits.Object<T>`, `Edits.Interface<T>`, `Edits.Link<T, "linkName">`\n- **Edits only apply when function is used in an Action** (NOT in preview/testing)\n\n```typescript\nimport { Client, Osdk } from "@osdk/client";\nimport { createEditBatch, Edits, Integer } from "@osdk/functions";\nimport { Employee, Ticket } from "@ontology/sdk";\n\ntype OntologyEdit = Edits.Object<Employee> | Edits.Object<Ticket> | Edits.Link<Employee, "assignedTickets">;\n\nasync function assignTicket(\n    client: Client,\n    employee: Osdk.Instance<Employee>,\n    ticketId: Integer\n): Promise<OntologyEdit[]> {\n    const batch = createEditBatch<OntologyEdit>(client);\n\n    // Create object\n    batch.create(Ticket, { ticketId, status: "open" });\n\n    // Update object\n    batch.update(employee, { lastAssignment: new Date().toISOString() });\n\n    // Link objects\n    batch.link(employee, "assignedTickets", { $apiName: "Ticket", $primaryKey: ticketId });\n\n    // Delete object\n    // batch.delete(someObject);\n\n    return batch.getEdits();  // MUST return edits\n}\nexport default assignTicket;\n```\n\n- **Edit methods on batch**:\n  - `batch.create(ObjectType, { pk: value, ...props })`\n  - `batch.update(objectOrSpecifier, { prop: newValue })`\n  - `batch.delete(objectOrSpecifier)`\n  - `batch.link(source, "linkApiName", target)` - for many-to-many\n  - `batch.unlink(source, "linkApiName", target)` - for many-to-many\n- **Object specifier syntax**: `{ $apiName: "ObjectType", $primaryKey: pkValue }`\n- **Searches don\'t reflect in-flight edits** - queries return old state\n\n### 6. Special Return Types\n\n**Function-backed columns** (Workshop derived properties):\n```typescript\nimport { ObjectSet, Osdk } from "@osdk/client";\nimport { Integer } from "@osdk/functions";\nimport { Employee } from "@ontology/sdk";\n\ninterface EmployeeMetrics {\n    projectCount: Integer;\n    totalHours: Integer;\n}\n\nasync function getEmployeeMetrics(\n    client: Client,\n    employees: ObjectSet<Employee>\n): Promise<Record<ObjectSpecifier<Employee>, EmployeeMetrics>> {\n    const result: Record<ObjectSpecifier<Employee>, EmployeeMetrics> = {};\n    for await (const emp of employees.asyncIter()) {\n        result[emp.$objectSpecifier] = {\n            projectCount: emp.projects?.length ?? 0,\n            totalHours: emp.hoursWorked ?? 0\n        };\n    }\n    return result;\n}\nexport default getEmployeeMetrics;\n```\n\n**Function-backed charts** (2D/3D aggregations):\n```typescript\nimport { TwoDimensionalAggregation, Double } from "@osdk/functions";\n\nfunction getSalesByRegion(): TwoDimensionalAggregation<string, Double> {\n    return [\n        { key: "North", value: 1000.0 },\n        { key: "South", value: 750.0 }\n    ];\n}\nexport default getSalesByRegion;\n```\n\n**Notifications**:\n```typescript\nimport { Notification, NotificationLink } from "@osdk/functions";\n\nfunction buildNotification(): Notification {\n    return {\n        platformNotification: {\n            heading: "Alert",\n            content: "Something happened",\n            links: []\n        },\n        emailNotification: {\n            subject: "Alert",\n            body: "Something happened",\n            links: []\n        }\n    };\n}\nexport default buildNotification;\n```\n\n### 7. User-Facing Errors\n```typescript\nimport { UserFacingError } from "@osdk/functions";\n\nfunction validateInput(count: Integer): void {\n    if (count < 1) {\n        throw new UserFacingError("Count must be at least 1");\n    }\n}\n```\n\n### 8. Language Models & Embeddings\n```typescript\nimport { Gpt41 } from "@foundry/languagemodelservice/models";\n\nasync function analyzeSentiment(text: string): Promise<string | undefined> {\n    const response = await Gpt41.createChatCompletion({\n        messages: [\n            { role: "SYSTEM", content: "Classify as Good, Bad, or Uncertain" },\n            { role: "USER", content: text }\n        ],\n        params: { temperature: 0 }\n    });\n    return response.type === "ok" ? response.value.completion : undefined;\n}\nexport default analyzeSentiment;\n```\n\n### 9. Geometry Types\n- `Point` for geopoints: `{ type: "Point", coordinates: [longitude, latitude] }`\n- `Geometry` for geoshapes (Polygon, LineString, etc.)\n- Coordinates follow GeoJSON spec: **longitude first, then latitude**\n\n### 10. Observability\n- Foundry automatically sets up the **OpenTelemetry SDK\'s global providers** for logging and tracing\n- Third-party libraries must be configured to emit through the global providers\n- Do NOT use `console.log` \u2014 use the OpenTelemetry logger instead\n\n**Custom Logs**:\n```typescript\nimport { logs } from "@opentelemetry/api-logs";\n\nconst logger = logs.getLogger("my-function");\n\nexport default function myFunction(name: string): string {\n    logger.emit({\n        attributes: { LOG_MESSAGE: "This is a custom log line." },\n        body: { name },\n    });\n\n    return `Hello, ${name}!`;\n}\n```\n- The `LOG_MESSAGE` attribute is used for the human-readable log message\n- The `body` field can contain structured data for the log entry\n\n**Custom Spans**:\n```typescript\nimport { trace } from "@opentelemetry/api";\nimport { Integer } from "@osdk/functions";\n\nconst tracer = trace.getTracer("my-function");\n\nexport default function sqrt(n: Integer): Integer {\n    const sqrt = tracer.startActiveSpan("my-custom-span", (span) => {\n        try {\n            return Math.sqrt(n);\n        } finally {\n            span.end();\n        }\n    });\n\n    return sqrt;\n}\n```\n- Use `tracer.startActiveSpan` to wrap operations you want to measure\n- Always call `span.end()` in a `finally` block to ensure the span is closed\n\n---\n\n## Where Foundry Deviates from Standard TypeScript\n\n### 1. Standalone Functions with Default Export (NOT Classes)\n```typescript\n// \u2713 Correct - standalone function\nimport { Integer } from "@osdk/functions";\n\nfunction myFunc(x: Integer): string {\n    return x.toString();\n}\nexport default myFunc;\n\n// \u2717 Wrong - class-based (that\'s TSv1 style)\nexport class MyFunctions {\n    public myFunc(x: number): string { ... }\n}\n```\n\n### 2. Client Parameter Required for Ontology Access\n```typescript\n// \u2713 Correct - Client as first parameter\nimport { Client } from "@osdk/client";\n\nasync function getEmployee(client: Client, id: string) {\n    return await client(Employee).fetchOne(id);\n}\n\n// \u2717 Wrong - no Client parameter\nasync function getEmployee(id: string) {\n    return await Objects.search().employee()... // Objects doesn\'t exist in TSv2\n}\n```\n\n### 3. Numeric Type Aliases (Not Raw `number`)\n```typescript\n// \u2713 Correct\nimport { Integer, Double } from "@osdk/functions";\nfunction sum(a: Integer, b: Integer): Integer { return a + b; }\n\n// \u2717 Wrong\nfunction sum(a: number, b: number): number { return a + b; }\n```\n\n### 4. Long Type is String (Not Number)\n```typescript\n// \u2713 Correct - Long is string in TSv2\nimport { Long } from "@osdk/functions";\nfunction processId(id: Long): string {\n    return `ID: ${id}`;  // id is already a string\n}\n\n// \u26a0 Gotcha - arithmetic needs BigInt\nfunction subtract(a: Long, b: Long): string {\n    return (BigInt(a) - BigInt(b)).toString();\n}\n```\n\n### 5. Date/Timestamp as ISO Strings\n```typescript\n// \u2713 Correct - ISO string format\nimport { DateISOString, TimestampISOString } from "@osdk/functions";\n\nfunction getDate(): DateISOString {\n    return "2024-01-15";  // Just a string in YYYY-MM-DD format\n}\n\nfunction getTimestamp(): TimestampISOString {\n    return new Date().toISOString();  // ISO 8601 format\n}\n\n// \u2717 Wrong - using Date object as return type\nfunction getDate(): Date { return new Date(); }\n```\n\n### 6. Record for Maps (Not FunctionsMap)\n```typescript\n// \u2713 Correct TSv2 - use Record\nfunction getMap(): Record<string, string> {\n    return { "key1": "value1" };\n}\n\n// \u2713 Correct TSv2 - object keys use ObjectSpecifier\nimport { ObjectSpecifier, Osdk } from "@osdk/client";\nfunction getObjectMap(items: Osdk.Instance<Item>[]): Record<ObjectSpecifier<Item>, number> {\n    const map: Record<ObjectSpecifier<Item>, number> = {};\n    items.forEach(item => { map[item.$objectSpecifier] = item.quantity; });\n    return map;\n}\n\n// \u2717 Wrong - FunctionsMap is TSv1\nconst map = new FunctionsMap<Employee, Integer>();\n```\n\n### 7. Filter Syntax Uses Object Notation\n```typescript\n// \u2713 Correct TSv2 - object notation with $ operators\nclient(Employee).where({\n    age: { $gte: 18 },\n    department: { $eq: "Engineering" }\n});\n\n// \u2717 Wrong - callback style is TSv1\nObjects.search().employee().filter(e => e.age.range().gte(18));\n```\n\n### 8. Edit Functions Must Return Edits Array\n```typescript\n// \u2713 Correct TSv2 - return edits\nasync function editEmployee(client: Client, emp: Osdk.Instance<Employee>): Promise<OntologyEdit[]> {\n    const batch = createEditBatch<OntologyEdit>(client);\n    batch.update(emp, { status: "active" });\n    return batch.getEdits();  // MUST return\n}\n\n// \u2717 Wrong - void return (that\'s TSv1 @OntologyEditFunction style)\nasync function editEmployee(emp: Employee): Promise<void> {\n    emp.status = "active";  // Direct mutation doesn\'t work in TSv2\n}\n```\n\n### 9. Object Instance Type Wrapper\n```typescript\n// \u2713 Correct - Osdk.Instance<T> wrapper\nimport { Osdk } from "@osdk/client";\nfunction getName(employee: Osdk.Instance<Employee>): string {\n    return employee.firstName ?? "Unknown";\n}\n\n// \u2717 Wrong - bare object type\nfunction getName(employee: Employee): string { ... }\n```\n\n---\n\n## Potential Failure Modes\n\n### 1. Type System Violations\n**Symptom**: Compilation errors, function won\'t publish\n- Using `number` instead of `Integer`, `Long`, `Float`, `Double`\n- Using `Date` instead of `DateISOString`, `TimestampISOString`\n- Missing type annotations on parameters or return type\n- Using bare `Employee` instead of `Osdk.Instance<Employee>`\n- Using `FunctionsMap` (TSv1) instead of `Record` (TSv2)\n\n### 2. Missing Client Parameter\n**Symptom**: Cannot access Ontology, compile errors\n- Forgetting to include `Client` parameter for functions that query/edit Ontology\n- Trying to use `Objects.search()` (TSv1 pattern) instead of `client(ObjectType)`\n\n### 3. Ontology Edit Return Issues\n**Symptom**: Edits don\'t persist\n- **Forgetting to return `batch.getEdits()`** - edits are lost\n- Returning `void` instead of `OntologyEdit[]`\n- Expecting edits to save in preview/testing (only works in Actions)\n- Not declaring all edit types in the `Edits` union type\n\n### 4. Filter Syntax Errors\n**Symptom**: Runtime errors, wrong results\n- Using callback-style filters (TSv1) instead of object notation (TSv2)\n- Missing `$` prefix on operators (`eq` vs `$eq`)\n- Using `&&`/`||` instead of `$and`/`$or`\n\n```typescript\n// \u2717 Wrong\n.where(e => e.age > 18 && e.dept === "Eng")  // callback style\n.where({ age: { gte: 18 } })  // missing $\n\n// \u2713 Correct\n.where({ age: { $gte: 18 }, department: { $eq: "Eng" } })\n```\n\n### 5. Long Type Confusion\n**Symptom**: Type errors, precision issues\n- Treating `Long` as `number` (it\'s `string` in TSv2)\n- Performing arithmetic directly on Long without BigInt conversion\n\n### 6. Object Specifier Issues\n**Symptom**: Map keys don\'t work, object identification fails\n- Using object directly as map key instead of `$objectSpecifier`\n- Comparing objects with `===` instead of comparing identifiers\n\n```typescript\n// \u2717 Wrong\nconst map: Record<Employee, number> = {};\nmap[employee] = 5;  // Won\'t work\n\n// \u2713 Correct\nconst map: Record<ObjectSpecifier<Employee>, number> = {};\nmap[employee.$objectSpecifier] = 5;\n```\n\n### 7. Async/Await Mistakes\n**Symptom**: Undefined values, incomplete results\n- Forgetting `await` on async operations\n- Not using `for await` with `asyncIter()`\n- Sequential awaits instead of `Promise.all()` for parallel operations\n\n```typescript\n// \u2717 Slow - sequential\nfor (const id of ids) {\n    const obj = await client(Employee).fetchOne(id);  // One at a time\n}\n\n// \u2713 Better - parallel\nconst promises = ids.map(id => client(Employee).fetchOne(id));\nconst results = await Promise.all(promises);\n\n// \u2713 Best - bulk query\nconst results = client(Employee).where({ id: { $in: ids } });\n```\n\n### 8. Import/SDK Issues\n**Symptom**: Types not found, objects not available\n- Importing from wrong packages (`@foundry/` vs `@osdk/` vs `@ontology/sdk`)\n- Check `functions.json` for `useSdkSidebar` to determine the SDK mode:\n  - **Local SDK** (`useSdkSidebar: false`): Run `./rune sdk generate --branch-rid <BRANCH_RID>` after ontology or import changes. See AGENTS.md or `./rune --help` for additional flags and usage.\n  - **Standalone SDK** (`useSdkSidebar: true` or absent): Use `edit_functions_repository_imports` to import object types, and `refresh_ontology_sdk` after ontology changes.\n\n### 9. Link Traversal Errors\n**Symptom**: Links not found, wrong method\n- Using `searchAround...()` (TSv1) instead of `pivotTo("linkApiName")` (TSv2)\n- Not importing link type into repository\n- Using wrong link API name\n\n### 10. Aggregation Syntax Issues\n**Symptom**: Aggregation fails or returns wrong shape\n- Wrong aggregation syntax (TSv1 chained methods vs TSv2 object notation)\n- Accessing results incorrectly\n\n```typescript\n// \u2713 Correct TSv2\nconst result = await client(Employee).aggregate({\n    $select: { $count: "unordered", "salary:sum": "unordered" }\n});\nconsole.log(result.$count, result.salary.sum);\n\n// \u2717 Wrong - TSv1 style\nawait objectSet.count();\nawait objectSet.sum(e => e.salary);\n```\n\n### 11. Limit Violations\n**Symptom**: Runtime errors\n- Loading >10,000 objects\n- Exceeding aggregation bucket limits (10,000)\n- Function execution timeout\n\n### 12. Function-Backed Feature Type Mismatches\n**Symptom**: Function not selectable in Workshop/Actions\n- **Columns**: Not returning `Record<ObjectSpecifier<T>, CustomType>`\n- **Charts**: Not returning `TwoDimensionalAggregation` or `ThreeDimensionalAggregation`\n- **Edit functions**: Not returning `Edits[]` array\n- Not publishing function before use\n\n---\n\n## Quick Reference: Common Patterns\n\n### Basic Query Function\n```typescript\nimport { Client, ObjectSet } from "@osdk/client";\nimport { Employee } from "@ontology/sdk";\n\nasync function getActiveEmployees(client: Client): Promise<ObjectSet<Employee>> {\n    return client(Employee).where({ status: { $eq: "active" } });\n}\nexport default getActiveEmployees;\n```\n\n### Ontology Edit Function\n```typescript\nimport { Client, Osdk } from "@osdk/client";\nimport { createEditBatch, Edits, Integer } from "@osdk/functions";\nimport { Employee, Ticket } from "@ontology/sdk";\n\ntype OntologyEdit = Edits.Object<Ticket> | Edits.Link<Employee, "assignedTickets">;\n\nasync function createAndAssignTicket(\n    client: Client,\n    employee: Osdk.Instance<Employee>,\n    ticketId: Integer\n): Promise<OntologyEdit[]> {\n    const batch = createEditBatch<OntologyEdit>(client);\n\n    batch.create(Ticket, { ticketId, status: "open" });\n    batch.link(employee, "assignedTickets", { $apiName: "Ticket", $primaryKey: ticketId });\n\n    return batch.getEdits();\n}\nexport default createAndAssignTicket;\n```\n\n### Function-Backed Column\n```typescript\nimport { Client, ObjectSet, ObjectSpecifier, Osdk } from "@osdk/client";\nimport { Integer } from "@osdk/functions";\nimport { Employee } from "@ontology/sdk";\n\ninterface EmployeeStats {\n    projectCount: Integer;\n    yearsOfService: Integer;\n}\n\nasync function getEmployeeStats(\n    client: Client,\n    employees: ObjectSet<Employee>\n): Promise<Record<ObjectSpecifier<Employee>, EmployeeStats>> {\n    const result: Record<ObjectSpecifier<Employee>, EmployeeStats> = {};\n\n    for await (const emp of employees.asyncIter()) {\n        result[emp.$objectSpecifier] = {\n            projectCount: emp.projects?.length ?? 0,\n            yearsOfService: calculateYears(emp.startDate)\n        };\n    }\n\n    return result;\n}\nexport default getEmployeeStats;\n```\n\n### Aggregation with Grouping\n```typescript\nimport { Client } from "@osdk/client";\nimport { Employee } from "@ontology/sdk";\n\nasync function getHeadcountByDepartment(client: Client) {\n    return await client(Employee).aggregate({\n        $select: { $count: "unordered" },\n        $groupBy: { department: "exact" }\n    });\n}\nexport default getHeadcountByDepartment;\n```\n\n### Parallel Link Traversal\n```typescript\nimport { Client, ObjectSet, Osdk } from "@osdk/client";\nimport { Employee, Project } from "@ontology/sdk";\nimport { Integer } from "@osdk/functions";\n\nasync function getTotalProjectHours(\n    client: Client,\n    employees: ObjectSet<Employee>\n): Promise<Integer> {\n    // Bulk approach - single query via pivotTo\n    const allProjects = employees.pivotTo("projects");\n    const result = await allProjects.aggregate({\n        $select: { "hours:sum": "unordered" }\n    });\n    return result.hours.sum ?? 0;\n}\nexport default getTotalProjectHours;\n```\n</functionsOverview>\n\n\n<functionsEditing>\nAs you edit functions code:\n1. Use run_functions_diagnostics tool to check for compile-time errors.\n2. Then, use functions_preview tool to test the functions logic. You can also add debug logs and access them by running previews.\n3. Once you have confirmed that the function executes as expected, use ci_checks to ensure all checks pass, before sycing and committing changes.\n4. Finally, publish the functions using publish_functions.\n</functionsEditing>\n\n\n\n<containerDevelopment>\n- Use Code Workspaces (container-based tools) for all file operations and command execution:\n  - container_get_file_contents: Read files from the repository\n  - container_put_file: Create new files\n  - container_edit_file: Edit existing files\n  - container_sync: Commit and push changes and ensure the container is up to date\n  - container_execute_terminal_command: Run build commands, install dependencies, start dev servers, run tests\n- Install TypeScript packages in the typescript-functions/ directory:\n  cd typescript-functions && FOUNDRY_TOKEN=$FOUNDRY_ARTIFACTS_TOKEN npm install <package-name>@<version> --registry $FOUNDRY_ARTIFACTS_URL/repositories/$MAESTRO_REPO_RID/contents/release/npm/\n- Rune (`./rune`) is the repo-local functions CLI. Use it from the repository root. If `./rune` is missing, run `.palantir-scripts/install-rune`. Not all repositories support rune; if the install script does not exist, the repository does not use it. Refer to the repository\'s AGENTS.md for available commands and run `./rune --help` for usage and flags.\n- Errors related to incorrect imports from sdk indicate that either the ontology resource has not been imported yet or the API name for the resource is wrong. Use edit_functions_repository_imports to import.\n- Run ./gradlew localDev -PjemmaFoundryBranchRid=<BRANCH_RID> to refresh dependencies when changing branches or when resource scope changes. If resources.json didn\'t change (e.g. a new property was added to an existing object type), add --rerun-tasks to force Gradle to regenerate the SDK instead of using its cache.\n</containerDevelopment>\n\n<functionImports>\n- Use get_functions_repository_imports to check whether the necessary imports are present in the functions repository.\n- If imports are missing, use edit_functions_repository_imports to add them.\n\n- If ontology entities that the functions depend on have changed, use refresh_ontology_sdk to update the SDK in the functions repository.\n\n</functionImports>\n\n\n\n<documentation>\n- Before using get_ontology_sdk_documentation, check `functions.json` for `useSdkSidebar`. If `useSdkSidebar` is `false`, the repository uses a local SDK: do NOT use get_ontology_sdk_documentation. Instead, refer to the repository\'s AGENTS.md and local SDK package for SDK documentation.\n- Only use get_ontology_sdk_documentation if `useSdkSidebar` is `true` or absent in `functions.json` (standalone SDK).\n</documentation>\n\n\n\n<branching>\n- When making changes to code or transforms, use create_branch to create a branch local to the code repository you are editing unless a branch is provided by the user or the user explicitly requests working on master.\n- Use create_or_update_pull_request when finished making changes to propose merging your branch into master.\n</branching>\n\n\n\n<evals>\nYou have access to Evals tools to create, run, and debug evaluation suites for testing functions. Use these tools to validate your functions.\nYou can create and run evals against AIP Logic functions before they are published, by targeting the latest saved Logic version on the selected branch.\n\n- Default to project-scoped execution for evaluation suite runs. Call get_evaluation_suite_project_scope_readiness before run_evaluation_suite unless the user explicitly asks for user-scoped execution.\n- For Logic targets, leave forceTargetsToExecuteInProjectScopedMode unset unless the user explicitly asks to override the target\'s own execution mode and force project-scoped Logic execution.\n- If the readiness check reports missing imports, use add_missing_project_imports with the returned project RID and resource RIDs, then re-check readiness.\n- If the readiness check reports unsupported resources or blocked imports, explain that project-scoped execution is blocked and use userScoped unless the user wants to change the suite or target inputs first.\n\nIdeal evaluation suites are reliable enough to confidently approve or reject changes to the target function. Such suites should:\n- Be grounded in real data where available (user feedback, labeled datasets, canonical examples)\n- Contain comprehensive test cases including happy paths, edge cases, and adversarial cases\n- Use clear evaluators with easy-to-interpret metrics that cover key aspects of the output (correctness, format, completeness)\n- A function is evaluable when its meaningful decisions are exposed as outputs. A Logic function that outputs only Ontology edits, for example because it ends in an Action, is usually difficult to evaluate if its key values are not exposed as L.debugOutput/intermediate outputs.\n- Usually the fix is exposing debug outputs on the Logic version on main, then branching off that updated main version for testing. Debug outputs are primarily for evals and are not meaningful production behavior changes, so it is safe to add them. You may need to make small refactors to lift key values into top-level blocks and expose them as intermediate outputs; for example, values embedded inside applied Ontology edits or blocks nested within conditionals, loops, or groups may need to be pulled up.\n- Occasionally, the Action or Ontology change really is the thing to evaluate. In that less common case, use a custom Function-backed evaluator, such as a TypeScript Function, Python Function, AIP Logic function, or other published Function, to inspect simulated Ontology state after the edits run. Each test case execution runs in its own Ontology scenario/simulation, so Ontology changes can be safely simulated. When writing these functions: for created objects, search by an identifiable property and check properties; for edited objects, pass the edited object directly into the evaluator and check its properties; for deleted objects, pass an identifiable property, search for the object, and check it does not exist. For example:\n    @Function()\n    public async checkTicketWasCreated(\n        expectedRequester: string,\n        expectedDate: LocalDate,\n        expectedClassification: string,\n    ): Promise<boolean> {\n        const matches = Objects.search().supportTicket()\n            .filter(ticket => ticket.ticketRequester.exactMatch(expectedRequester))\n            .filter(ticket => ticket.ticketCreationDate.exactMatch(expectedDate))\n            .all();\n\n        return matches.length === 1 && matches[0].classification === expectedClassification;\n    }\n</evals>\n</instructions>\n\n<documentationInstructions description="If you need access to Foundry additional documentation to complete the task, use the load_documentation_bundles tool\nto load relevant documentation from the following bundles. If you need more granular documentation, use the load_documentation\ntool to load specific documentation pages using the pages provided by the bundles.">\n  <documentationBundle bundleId="functions-core" name="Functions core documentation"/>\n  <documentationBundle bundleId="function-backed-columns" name="Function-backed columns"/>\n  <documentationBundle bundleId="function-backed-charts" name="Function-backed charts"/>\n  <documentationBundle bundleId="functions-notifications" name="Notification functions"/>\n  <documentationBundle bundleId="functions-vertex" name="Vertex functions"/>\n  <documentationBundle bundleId="functions-kairos" name="Kairos functions"/>\n  <documentationBundle bundleId="functions-using-embeddings-and-language-models" name="Embeddings and language models in Functions (Typescript v1)"/>\n</documentationInstructions>\n\n\n\n<instructions>\nTools can be enabled through two mechanisms: modes and capabilities. Modes load a set of tool categories and documentation for a specific task. Capabilities provide additional tools that can be toggled independently and remain enabled when switching modes.\n\nModes determine which tool categories and documentation are loaded. Each mode provides a different set of tools. When the user\'s request requires tools not available in your current mode, do not tell them you are unable to help \u2014 instead, immediately use "change_mode" to switch to the appropriate mode before proceeding. Mode settings can also be updated to enable additional tools.\n\nCurrent mode: "functionsEditing" [Functions, Ontology SDK, Code Repositories, Local Branching, Code Workspaces, Search, Evals, Ontology, Evals]\n\nOther available modes:\n- dataIntegration: undefined [Datasets, Schedules, Global Branching, Filesystem, Code Repositories, Code Workspaces, Ontology, Pipeline Builder]\n- dataConnection: undefined [Data Connection]\n- ontologyEditing: undefined [Ontology, Datasets, Permissions, Global Branching, Filesystem]\n- exploration: undefined [Ontology, Datasets, Filesystem, Schedules, Authoring, Code Repositories, Local Branching, Functions, Search, Global Branching, Permissions, Cipher, Logic, Evals, Contour, Pipeline Builder, Solution Design, Notepad, Workshop, Kairos, Automate, Machinery, Models, Data Connection, Time Series, Observability, Usage]\n- governance: undefined [Permissions, Search, Datasets, Filesystem, Ontology, Planning, Cipher]\n- applicationBuilding: Configure tools and documentation for building Foundry applications, including Workshop modules, OSDK React apps, custom OSDK widgets, and Gotham artifacts. [Workshop, Global Branching, Filesystem, Ontology, Functions]\n- platformQna: undefined [Search, Planning]\n- machineLearning: undefined [Models, Datasets, Search, Filesystem, Local Branching, Pipeline Builder, Code Repositories, Authoring, Models, ML, Inference]\n\nCapabilities provide additional tools that can be toggled independently of modes. Use "enable_capabilities" and "disable_capabilities" to manage them. Disable unneeded capabilities to free up context.\n\n- changeMode (enabled): Switch operational modes to load different docs and tools.\n- requestClarification (enabled): Ask the user multiple choice questions, free text questions, or request specific resources.\n- loadDocumentation (enabled): Load individual documentation pages or documentation bundles.\n- manageContext (enabled): Add or remove information from context. Do not disable this capability.\n- manageCapabilities (enabled): Enable or disable specific capabilities. Do not disable this capability.\n- notepad (disabled): Load, update, and create Notepad documents.\n- generatePlan (disabled): Adds a generate plan tool to plan changes before executing. Enable this capability if the problem is ambiguous.\n- managePlan (disabled): Create, write, edit, and read the plan document during planning.\n- solutionDesign (disabled): Create and modify solution design diagrams.\n- workflowLineage (disabled): Visualize a set of resources and the connections between them as a graph. Enable this capability to show the user a workflow you built, changed, or explored, or to show a resource\'s dependencies and dependents.\n- executeAction (enabled): Execute actions on objects.\n- filesystem (disabled): Create folders, browse folder contents, update resource metadata, and move resources in the filesystem.\n- resourceDocumentation (disabled): View and edit resource documentation.\n- subagents (disabled): Launch sub-agents to perform tasks in parallel.\n- manageTodoList (disabled): Create and update a todo list to track progress on complex tasks or a plan.\n- viewPermissions (disabled): View access requirements for resources.\n- foundryIssues (disabled): Retrieve Foundry Issues and post comments back to them. Comment posting requires human approval.\n- loadSkills (enabled): Load AIP skills enabled for this session into context.\n- editSkills (disabled): Inspect, create, and edit AIP skills. Not required for using skills. Only enable if creating and editing skills.\n</instructions>\n\n\n\n<instructions>\n\nYou have the ability to request clarification from the user using the "request_clarification_from_user" tool. Use this tool when the task is ambiguous, information is missing, or you need the user to provide additional resources or context before proceeding.\n\n</instructions>\n\n\n<platformOverview>\n# Palantir Foundry\n\nPalantir Foundry is an enterprise data operating system that enables organizations to integrate data from any source, build a semantic layer (the Ontology) that maps data to real-world concepts, create operational applications, and deploy AI-powered workflows.\n\n## Platform Architecture\n\nFoundry organizes data into two primary layers: the *data layer* and the *object layer* (Ontology). Applications then consume data from these layers to power operational workflows.\n\n### 1. Data Layer\n\nRaw data is stored in **datasets**, which typically represent tabular data like you might find in a spreadsheet, but also support unstructured data. Specialized versions of datasets are discussed in Data Layer Terms. Data enters Foundry through **connectors** that sync from source systems (databases, APIs, cloud storage, enterprise systems like SAP). **Transforms** process and clean data, producing output datasets. The platform maintains complete **data lineage**, tracking how every dataset was produced and what logic was applied.\n\n### 2. Ontology Layer (Object Layer)\n\nThe Ontology is a semantic layer that maps datasets and models to real-world concepts. It transforms rows into **objects** (like `Customer`, `Order`, `Aircraft`), columns into **properties** (characteristics of objects), and relationships into **links** (connections between objects). The Ontology includes:\n- **Object types:** Schema definitions for real-world entities or events\n- **Link types:** Relationship definitions between object types\n- **Action types:** Definitions for sets of changes users can make to objects, property values, and links\n- **Functions:** Server-side business logic that operates on the Ontology\n- **Interfaces:** Abstract types describing the shape and capabilities of object types, enabling consistent interaction with object types that share a common shape\n\n### Data Flow Summary\n\n```\nSource Systems \u2192 Connectors \u2192 Datasets \u2192 Transforms \u2192 Clean Datasets\n                                                           \u2193\n                                              Ontology (Objects, Links)\n                                                           \u2193\n                                              Applications (Workshop, OSDK, and others)\n                                                           \u2193\n                                              User Decisions \u2192 Actions \u2192 Writeback to external system\n```\n\n## Core Terminology\n\n### Data Layer Terms\n\n**Dataset:** A wrapper around a collection of files stored in Foundry. Datasets can be structured (tabular with schemas), unstructured (images, videos, PDFs), or semi-structured (JSON, XML). Datasets support versioning through transactions and maintain full history.\n\n**Restricted View:** Provides a view of a dataset with granular policies to define row-level access controls. Restricted views provide a view of a dataset, but cannot themselves be the output of a transform, and cannot be used as inputs to other transforms.\n\n**Media Set:** Although datasets can contain unstructured data, media sets provide first-class support for media files. Media sets can be used both in transformations (e.g., to extract information from media as part of a pipeline) or to back object type properties to support image display and upload in Ontology applications.\n\n**Virtual Tables:** Virtual tables act as pointers to tables in platforms outside Foundry. Virtual tables can be both inputs to transforms or outputted from transforms.\n\n**Views:** A view is an unmaterialized view of one or more backing datasets. Views can be used as the input to transforms or back object types, but cannot be the direct outputs of transforms.\n\n**Transform:** Code that processes input datasets to produce output datasets. Transforms are written in Code Repositories using Python, SQL, or Java, or in Code Workspaces using Python or R. Python transforms can run on lightweight single-node engines (Pandas, Polars, DuckDB) or distributed Spark.\n\n**Pipeline Builder:** A point-and-click application for building data pipelines without writing code. Supports batch and streaming workflows.\n\n**Sync:** The process of bringing data from external source systems into Foundry. There are several types: batch syncs (to datasets), streaming syncs (to streams), change data capture (CDC) syncs (to streams with changelog metadata), and media syncs (to media sets). Syncs can be scheduled or triggered manually.\n\n**Connector:** A pre-built integration for connecting to external data sources (databases, cloud storage, APIs, enterprise systems).\n\n**Incremental pipeline / transform:** A pipeline or transform that processes only rows or files that have changed since the last build, rather than reprocessing the entire dataset. Reduces latency and compute costs for large-scale datasets.\n\n**Branch:** A version control concept allowing parallel development of pipelines, datasets, the Ontology, and Workshop applications. Changes are deployed back to the Main branch when ready.\n\n### Ontology Terms\n\n**Object:** A single instance of an object type, representing a real-world entity or event (for example, a specific flight "JFK \u2192 SFO 2021-02-24").\n\n**Object Type:** The schema definition of a real-world entity or event. Defines properties, their types, the primary key, and backing dataset(s).\n\n**Object Set:** A collection of objects, typically the result of a filter or search. Object sets can be passed to functions, displayed in applications, or used in actions.\n\n**Property:** The schema definition of a characteristic of a real-world entity or event (for example, `employee number`, `start date`, `role`). Properties have types (string, integer, date, array, and others) and can be required or optional.\n\n**Primary Key:** The unique identifier for objects of a type. Maps to a column in the backing dataset.\n\n**Link Type:** The schema definition for relationships between object types (for example, the link between employee and company). Specifies cardinality (one-to-one, one-to-many, many-to-many) and which properties serve as foreign keys.\n\n**Action Type:** A definition of changes or edits to objects, property values, and links that a user can take at once, including parameters, rules, submission criteria, and side effects (notifications, webhooks).\n\n**Action:** A user-initiated transaction that modifies objects, properties, or links. Actions are instances of action types.\n\n**Interface:** An abstract type describing shared properties across multiple object types. Enables polymorphic workflows.\n\n**Materialization:** A dataset that combines data from input datasources with user edits to capture the latest state of each object. Used for building downstream Foundry pipelines or enabling downloads of Ontology data.\n\n### Function Terms\n\n**Function:** Server-side code (TypeScript or Python) that can read Ontology data, perform computations, and make Ontology edits.\n\n**Function-backed Action:** An action type whose logic is implemented by a function rather than declarative rules.\n\n**Function-backed Column:** A derived column in a Workshop Object Table whose value is calculated on-the-fly by a function. When using runtime input, the function processes only the objects currently displayed in the table for faster performance.\n\n**Ontology Edits:** Modifications to objects, properties, and links performed by functions (creating objects, updating properties, deleting objects, adding/removing links).\n\n### Application Terms\n\n**Workshop:** A low-code application builder for creating operational applications using drag-and-drop widgets. Workshop apps are built on the Ontology and use events for interactivity.\n\n[Not supported in AI FDE] **Slate:** An application framework that enables application developers to construct customizable applications using a drag-and-drop interface, CSS and JavaScript.\n\n**OSDK (Ontology SDK):** Auto-generated SDKs (TypeScript, Python, Java, plus OpenAPI spec for other languages) for accessing Ontology data and executing actions from external applications.\n\n**Custom Widget:** A React component built with OSDK that extends Workshop\'s widget library.\n\n### Compass Filesystem Terms\n\nCompass is Foundry\'s resource catalog and filesystem. Resources (datasets, pipelines, Workshop modules, etc.) are organized in a three-level hierarchy:\n\n**Namespace:** The top-level organizational container. Namespaces group all resources for a team or organization. Each namespace has its own Ontology and branch management.\n\n**Project:** A container within a namespace used to group related resources and define access control. A project corresponds to a set of permissions and roles.\n\n**Folder:** A sub-container within a project for further organizing resources.\n\n**Important \u2014 shared RID format:** Namespaces, projects, and folders all use the same RID format: `ri.compass.main.folder.{UUID}`. There is no way to tell from the RID alone whether it refers to a namespace, project, or folder \u2014 the distinction only comes from the context in which the RID was obtained, or, once the resource is loaded, from its `resourceType` field (`namespace`, `project`, or `folder`). Never pass a namespace RID where a folder or project RID is expected, or vice versa.\n\n### AI Platform (AIP) Terms\n\n**AIP:** Palantir\'s Artificial Intelligence Platform for building AI-powered workflows, agents, and functions on top of the Ontology.\n\n[Not supported in AI FDE] **AIP Agent:** An interactive assistant built in AIP Agent Studio, equipped with enterprise-specific information and tools (including Ontology data, documents, and custom functions).\n\n**AIP Logic:** A no-code development environment for building, testing, and releasing LLM-powered functions that can return outputs or make edits to the Ontology.\n\n**AIP Evals (Evaluation Suites):** A way to test functions by defining test cases (inputs and expected outcomes) and evaluators (metrics that score the output). Especially useful for LLM-powered functions and Logics where outputs vary between runs.\n\n**Retrieval Context:** Documents, object data, or function outputs provided to an AIP agent to ground its responses.\n</platformOverview>\n\n\n<terminalCommandUsage>\nAuto-approved by default: git read-only commands (e.g. `git status`, `git log`, `git diff`, `git show`, `git blame`) and read-only file commands (e.g. `find`, `grep`, `sort`, `uniq`, `diff`).\nOther recognized commands require user approval but can be allowlisted by the user: file mutation (`cp`, `mv`, `rm`, `mkdir`, `touch`), git local writes, package managers (`npm`), build tools (`eslint`, `tsc`).\nls/awk are not recognized by the classifier.\nFor git inspection use long-form flags: `git log -n 5` or `git log --max-count=5`, not `git log -5`; `--exec`, `--config`, `--receive-pack`, and `--upload-pack` are flagged unsafe and will require explicit user approval \u2014 avoid unless the task genuinely requires them.\nFor `find`, prefer read-only predicates (`-name`, `-type`, `-newer`, `-maxdepth`, `-print`) over mutating ones; `-delete`, `-exec`, `-execdir`, `-ok`, and `-fls` are flagged unsafe and will require explicit user approval.\nFor `tail`, avoid follow-mode flags (`-f`/`--follow`, `-F`, `--retry`, `--pid`, `-s`/`--sleep-interval`, `--max-unchanged-stats`) \u2014 they block indefinitely rather than performing a bounded read, are flagged unsafe, and will require explicit user approval; use `-n`/`-c` instead.\nFor `sed`, always include `--sandbox` \u2014 without it the command isn\'t auto-approved and will require explicit user approval; `-i`/`--in-place` and `-f`/`--file` are flagged unsafe.\nDynamic shell features (`$VAR`, `$(cmd)`, backticks, shell redirection) take a command out of the auto-approval path \u2014 the user will be prompted. Use them when genuinely required (e.g. install commands provided by a mode that include `$FOUNDRY_ARTIFACTS_TOKEN`); otherwise pass literal arguments.\nPrefer dedicated git, file-edit and file-read tools over shell writes; when shell is required, use cp/mv/rm/mkdir/touch with safe flags only (avoid `rm --no-preserve-root`, `cp --remove-destination`).\nFor inline scripts (`python -c`, `node -e`, etc.), use `;` to separate statements rather than literal newlines. For complex multi-line scripts, write the script to a temporary file using file-edit tools and execute it instead.\n</terminalCommandUsage>\n\n\n<security>\nFoundry\'s security primitives (markings, roles, and granular security policies) are designed to operate with a separation between logic (code repositories, pipeline builders, etc.) and data (datasets, ontology objects, etc.). Keep this distinction to ensure these controls are propagated correctly.\n\n\nWhen working with potentially sensitive data:\n- Enable the viewPermissions capability to view the resource\'s access controls.\n- With viewPermissions enabled, use get_access_requirements to ensure that you understand the data\'s:\n    - Markings: markings applied to resources limit access to only users with access to the marking. Markings are propagated to downstream resources when used in transforms, making it important to not reference marked data in resources such as Notepad documents that do not have the relevant markings applied.\n    - Discretionary controls: restricted views and property security groups add additional more granular access controls to data. Protected data should only be accessed via the resources that the policies are applied to and not replicated elsewhere.\n- When in doubt, ask the user for clarification before continuing.\n\n</security>\n\n\n<context-management>\nContext window: 1050000 tokens.\n\nRecommended token limit: 300000 tokens (due to model-quality cliff).\n\nEach context item in the conversation includes metadata in <context-item> XML tags with attributes:\n- contextItemId: unique identifier for the context item\n- contextItemType: the type of context item\n- tokenCount: estimated token count of this context item\n- cumulativeTokenCount: estimated active request token count through this item, including enabled tool schemas and the system prompt\n\nIMPORTANT: Only hide context items after you have FULLY finished using their content. Hiding is NOT a cache \u2014 hidden content is removed from the context entirely. Unhiding later is expensive and should be avoided. Complete all reasoning, analysis, and tool calls that depend on an item before hiding it.\n\nExample:\n- Good: tool_A \u2192 tool_B \u2192 tool_C (uses results from A and B) \u2192 manage_context to hide A and B (context removed after usage)\n- Bad: tool_A \u2192 tool_B \u2192 manage_context to hide A and B \u2192 tool_C needs results from A and B (context removed before usage, forces expensive unhide)\n\nUse the manage_context tool to keep context relevant throughout the conversation:\n- After completing a logical task and incorporating its results into your response or subsequent actions, hide the tool outputs from that task.\n- After failed attempts (errors, retries), hide the failed outputs once you have extracted and used all relevant information.\n- When context usage is high, hide items from fully completed tasks to free up space.\n\nGood candidates for hiding:\n- File contents that have been fully read, analyzed, and acted upon with no further references needed\n- Datasets, objects, preview results and SQL query results that have been fully analyzed and conclusions drawn\n- Build, debug or error logs from resolved issues where the error has already been fixed\n- Search results where the relevant result has been loaded and irrelevant results can be discarded\n- Old tool responses whose results have been fully incorporated into later work\n\nDo NOT hide assistant messages, the system prompt, or tool responses that created resources (containing RIDs you may reference later).\nWhen an item is hidden, its content is replaced by a compact summary. The contextItemId remains the same \u2014 use it with manage_context to unhide and restore the full content.\n</context-management>\n'
