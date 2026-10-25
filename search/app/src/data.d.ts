// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

// Types the 2 MB generated file by declaration instead of letting tsc infer
// a type from its contents.
declare module "*/generated/data.json" {
  const data: import("./types").Data;
  export default data;
}
