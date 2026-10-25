// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

// Shape of generated/data.json, written by search/build.py. Empty and false
// fields are dropped by the build, so most fields are optional.

export interface Store {
  id: string;
  name: string;
  source: string;
}

/** Order-level amounts, for exports that have them (Adafruit). */
export interface Summary {
  subtotal?: string;
  shipping?: string;
  tax?: string;
  discount?: string;
}

export interface Item {
  name: string;
  qty: string;
  asin?: string;
  unit?: string;
  total?: string;
  url?: string;
  /** m.media-amazon.com image ID from images.json. */
  image?: string;
  /** Known to have no image: skip straight to the placeholder. */
  noImage?: boolean;
  /** Store's product category, e.g. "Electronics" (Amazon exports from late 2026). */
  department?: string;
  /** Store's own product number (Adafruit PID). */
  pid?: string;
  /** Direct product image URL, for stores whose export or lookup provides one. */
  imageUrl?: string;
}

export interface Order {
  store: string;
  id: string;
  date: string;
  currency: string;
  items: Item[];
  /** "" (absent) means the normal terminal state. */
  status?: string;
  total?: string;
  digital?: boolean;
  site?: string;
  url?: string;
  shipMethod?: string;
  summary?: Summary;
}

export interface Data {
  generated: string;
  stores: Store[];
  orders: Order[];
}
