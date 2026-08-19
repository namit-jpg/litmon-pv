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
  // Manual entry, for products the RxNorm catalogue does not carry.
  const [manual, setManual] = useState({
    name: "",
    inn: "",
    brands: "",
    synonyms: "",
    query_text: "",
  });
  const [adding, setAdding] = useState(false);

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

  /** Create a product without an RxNorm concept.
   *
   *  RxNorm is a United States vocabulary, so non-US molecules and brands —
   *  sodium fusidate, most Indian brands — are simply absent from the picker.
   *  They are still monitorable: the search string is free text. What this path
   *  gives up is the catalogue's derived substances and ATC code, so the
   *  substance has to be named here by hand.
   */
  async function addManualProduct() {
    const name = manual.name.trim();
    if (!name) return;
    setAdding(true);
    setError("");
    setMessage("");
    try {
      const list = (value: string) =>
        value.split(",").map((item) => item.trim()).filter(Boolean);
      const created = await api.createProduct({
        name,
        inn: manual.inn.trim() || undefined,
        brands: list(manual.brands),
        // Synonyms widen the generated query, which is the whole point for a
        // brand whose own name barely appears in the literature.
        synonyms: list(manual.synonyms),
        query_text: manual.query_text.trim() || undefined,
      });
      setManual({ name: "", inn: "", brands: "", synonyms: "", query_text: "" });
      setMessage(
        `Added ${created.name}. Review its search string under Search & schedule before relying on it.`,
      );
      await load();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setAdding(false);
    }
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

      <details className="card manual-product no-print">
        <summary>
          <span>Add a product the catalogue does not carry</span>
          <span className="muted">
            for non-US molecules and brands absent from RxNorm
          </span>
        </summary>
        <div className="manual-product-body">
          <p className="muted">
            The drug catalogue is RxNorm, which covers the United States market —
            so products licensed elsewhere will not appear in the picker even
            though their literature is fully searchable. Enter one here and name
            its substance yourself; everything downstream behaves normally.
          </p>
          <div className="form-grid">
            <label>
              Product name
              <input
                value={manual.name}
                onChange={(event) =>
                  setManual({ ...manual, name: event.target.value })
                }
                placeholder="e.g. Sodium fusidate"
              />
            </label>
            <label>
              INN / active substance
              <input
                value={manual.inn}
                onChange={(event) =>
                  setManual({ ...manual, inn: event.target.value })
                }
                placeholder="e.g. fusidic acid"
              />
            </label>
            <label>
              Brand names
              <input
                value={manual.brands}
                onChange={(event) =>
                  setManual({ ...manual, brands: event.target.value })
                }
                placeholder="Comma-separated"
              />
            </label>
            <label>
              Search aliases
              <input
                value={manual.synonyms}
                onChange={(event) =>
                  setManual({ ...manual, synonyms: event.target.value })
                }
                placeholder="Other names the literature uses"
              />
            </label>
          </div>
          <label>
            PubMed query
            <textarea
              rows={2}
              value={manual.query_text}
              onChange={(event) =>
                setManual({ ...manual, query_text: event.target.value })
              }
              placeholder="Leave blank to generate one from the names above"
            />
          </label>
          <div className="row-actions">
            <button
              className="btn primary"
              disabled={adding || !manual.name.trim()}
              onClick={addManualProduct}
            >
              {adding ? "Adding…" : "Add product"}
            </button>
            <span className="muted">
              A first search string is created with it, and both are audited.
            </span>
          </div>
        </div>
      </details>

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
