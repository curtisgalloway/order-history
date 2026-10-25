// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import type { Item } from "./types";

/* Image cascade for Amazon ASINs: stage -1 = m.media-amazon.com CDN by image
   ID (from the images.json cache built by fetch_images.py, most reliable),
   stage 0 = images-na P/<ASIN> (1x1 GIF when missing, so check naturalWidth
   on load), stage 1 = legacy associates widget (may be DNS-blocked, so
   onerror), stage 2 = give up and show the placeholder. */
const GIVE_UP = 2;

function imgSrc(stage: number, asin: string, id?: string): string {
  if (stage === -1) return "https://m.media-amazon.com/images/I/" + id + "._SL160_.jpg";
  if (stage === 0)
    return "https://images-na.ssl-images-amazon.com/images/P/" + asin + ".01._SL160_.jpg";
  return (
    "https://ws-na.amazon-adsystem.com/widgets/q?_encoding=UTF8&ASIN=" + asin +
    "&Format=_SL160_&ID=AsinImage&MarketPlace=US&ServiceVersion=20070822&WS=1"
  );
}

// The virtual list unmounts rows as they scroll away; remember how far each
// ASIN got so a remount does not replay the failed stages.
const reached = new Map<string, number>();

export function Thumb({ item, label }: { item?: Item; label: string }) {
  const asin = item?.asin ?? "";
  const first = item?.image ? -1 : item?.noImage ? GIVE_UP : 0;
  const [stage, setStage] = useState(() => reached.get(asin) ?? first);
  const [direct, setDirect] = useState(!!item?.imageUrl);

  if (item?.imageUrl && direct)
    return <img loading="lazy" alt="" src={item.imageUrl} onError={() => setDirect(false)} />;
  if (item?.imageUrl) return <div className="ph">no image</div>;
  if (!item || !asin) return <div className="ph">{item && !item.pid ? "no asin" : label}</div>;
  if (stage >= GIVE_UP) return <div className="ph">no image</div>;

  const next = () => {
    const s = stage + 1;
    reached.set(asin, s);
    setStage(s);
  };
  return (
    <img
      loading="lazy"
      alt=""
      src={imgSrc(stage, asin, item.image)}
      onLoad={(e) => {
        if (e.currentTarget.naturalWidth <= 1) next();
      }}
      onError={next}
    />
  );
}
