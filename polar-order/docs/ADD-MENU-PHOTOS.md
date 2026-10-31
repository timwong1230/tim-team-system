# How to add product photos

## Quick method

1. Export a square-ish photo (recommended **800×600** or **1:1**, JPG/PNG/WebP).
2. Save it into:

```text
polar-order/static/images/menu/<item-id>.jpg
```

Example: Regular Shisha → `static/images/menu/shisha-regular.jpg`

3. In `polar-order/data/menu.json`, set the `image` field on that item:

```json
{
  "id": "shisha-regular",
  "name": "Regular Shisha",
  "price": 398,
  "image": "/static/images/menu/shisha-regular.jpg"
}
```

4. Restart the server (or just refresh — menu syncs on startup).

## Tips

- File name should match `item id` when possible.
- Keep photos under ~500KB for fast iPhone loading.
- If `image` is missing, the guest menu still works (text only).
- Sample placeholders are already included for: `shisha-regular`, `shisha-change`, `aries`, `fries`.
- **Do not run bottle-style rembg background blur on shisha photos** — the pipe/hose is often
  mis-segmented and the subject itself ends up blurred. Keep the venue shoot originals.
