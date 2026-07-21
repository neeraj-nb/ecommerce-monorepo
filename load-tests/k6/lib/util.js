// Tiny local helper instead of pulling in jslib.k6.io -- keeps a load-test run
// free of an external CDN fetch as a dependency at run time.
export function randomIntBetween(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// Simple approximation of a Zipfian/power-law access pattern: a small "hot"
// fraction of products gets a disproportionate share of traffic, matching
// real catalogs (a few popular items dominate) far better than picking
// uniformly at random across the whole pool.
export function pickWeightedProduct(productIds, hotFraction = 0.2, hotTrafficShare = 0.8) {
  const hotCount = Math.min(
    productIds.length - 1,
    Math.max(1, Math.floor(productIds.length * hotFraction))
  );
  if (hotCount >= productIds.length - 1 || Math.random() < hotTrafficShare) {
    return productIds[randomIntBetween(0, hotCount)];
  }
  return productIds[randomIntBetween(hotCount + 1, productIds.length - 1)];
}
