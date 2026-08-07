import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ActiveIngredient, api, Product, SearchSchedule, User } from "../api";

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [ingredients, setIngredients] = useState<ActiveIngredient[]>([]);
  const [schedules, setSchedules] = useState<SearchSchedule[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const [productRows, userRows, ingredientRows, scheduleRows] = await Promise.all([
        api.products(),
        api.users(),
        api.activeIngredients(),
        api.searchSchedules(),
      ]);
      setProducts(productRows);
      setUsers(userRows);
      setIngredients(ingredientRows);
      setSchedules(scheduleRows);
    } catch (caught) {
      setError(String(caught));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const schedulesByProduct = useMemo(() => {
    const result = new Map<number, SearchSchedule[]>();
    for (const schedule of schedules) {
      result.set(schedule.product_id, [...(result.get(schedule.product_id) || []), schedule]);
    }
    return result;
  }, [schedules]);

  function update(id: number, patch: Partial<Product>) {
    setProducts((rows) => rows.map((product) => product.id === id ? { ...product, ...patch } : product));
  }

  async function save(product: Product) {
    setSaving(product.id);
    setError("");
    setMessage("");
    try {
      await api.updateProduct(product.id, {
        name: product.name,
        inn: product.inn || null,
        brands: product.brands,
        synonyms: product.synonyms,
        atc_code: product.atc_code || null,
        mah: product.mah || null,
        markets: product.markets,
        primary_reviewer_id: product.primary_reviewer_id || null,
        active_ingredient_ids: product.active_ingredients.map((item) => item.id),
      });
      setMessage(`${product.name} was updated and the change was audited.`);
      await load();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setSaving(null);
    }
  }

  function toggleIngredient(product: Product, ingredient: ActiveIngredient) {
    const selected = product.active_ingredients.some((item) => item.id === ingredient.id);
    update(product.id, {
      active_ingredients: selected
        ? product.active_ingredients.filter((item) => item.id !== ingredient.id)
        : [...product.active_ingredients, ingredient],
    });
  }

  return (
    <div>
      <div className="shd">
        <span className="eyebrow">Step 1 · Product configuration</span>
        <h1>Products</h1>
        <p className="sub">
          Product, brand, INN, active ingredient, licence facts, monitoring
          cadence, and review ownership remain explicit and independently editable.
        </p>
      </div>
      <div className="row-actions no-print">
        <Link className="btn primary" to="/product-search">Add product from drug catalogue</Link>
        <Link className="btn" to="/schedule">Manage schedules</Link>
      </div>
      {message ? <div className="ok-banner">{message}</div> : null}
      {error ? <div className="error">{error}</div> : null}

      {products.map((product) => {
        const productSchedules = schedulesByProduct.get(product.id) || [];
        return (
          <section className="card product-editor" key={product.id}>
            <div className="page-head compact">
              <div><h2>{product.name}</h2><p className="muted">Product #{product.id}</p></div>
              <button className="btn primary no-print" disabled={saving === product.id} onClick={() => save(product)}>{saving === product.id ? "Saving…" : "Save product"}</button>
            </div>
            <div className="form-grid">
              <label>Product name<input value={product.name} onChange={(event) => update(product.id, { name: event.target.value })} /></label>
              <label>INN / generic name<input value={product.inn || ""} onChange={(event) => update(product.id, { inn: event.target.value })} /></label>
              <label>Brand names<input value={product.brands.join(", ")} onChange={(event) => update(product.id, { brands: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} placeholder="Comma-separated" /></label>
              <label>Synonyms<input value={product.synonyms.join(", ")} onChange={(event) => update(product.id, { synonyms: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} placeholder="Comma-separated" /></label>
              <label>ATC code<input value={product.atc_code || ""} onChange={(event) => update(product.id, { atc_code: event.target.value.toUpperCase() })} /></label>
              <label>Marketing authorisation holder<input value={product.mah || ""} onChange={(event) => update(product.id, { mah: event.target.value })} /></label>
              <label>Markets<input value={product.markets.join(", ")} onChange={(event) => update(product.id, { markets: event.target.value.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean) })} placeholder="IN, GB" /></label>
              <label>Responsible reviewer<select value={product.primary_reviewer_id || ""} onChange={(event) => update(product.id, { primary_reviewer_id: event.target.value ? Number(event.target.value) : null })}><option value="">Use assignment fallback</option>{users.map((user) => <option key={user.id} value={user.id}>{user.full_name} · {user.role.replace(/_/g, " ")}</option>)}</select></label>
            </div>
            <fieldset>
              <legend>Active ingredients / APIs</legend>
              <div className="checklist">
                {ingredients.map((ingredient) => (
                  <label key={ingredient.id}><input type="checkbox" checked={product.active_ingredients.some((item) => item.id === ingredient.id)} onChange={() => toggleIngredient(product, ingredient)} />{ingredient.name}{ingredient.inn && ingredient.inn !== ingredient.name ? ` · INN ${ingredient.inn}` : ""}</label>
                ))}
              </div>
            </fieldset>
            <div className="report-facts">
              <strong>Monitoring frequency</strong>
              {productSchedules.length === 0 ? <p className="muted">No schedule configured.</p> : productSchedules.map((schedule) => <span className="pill" key={schedule.id}>{schedule.frequency} · {schedule.is_active ? "active" : "paused"}</span>)}
            </div>
          </section>
        );
      })}
      {products.length === 0 ? <div className="empty">No monitored products. Add one from Product search.</div> : null}
    </div>
  );
}
