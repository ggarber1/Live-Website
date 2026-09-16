import { useEffect, useState } from 'react'
import { Link, Route, Routes, useNavigate, useParams } from 'react-router'

import { createRecipe, getRecipe, listRecipes, updateRecipe, type Recipe, type RecipeDraft } from './api'
import RecipeForm from './RecipeForm'
import RecipePage from './RecipePage'

export default function RecipesPage() {
  return (
    <Routes>
      <Route index element={<RecipeList />} />
      <Route path="new" element={<NewRecipe />} />
      <Route path=":id" element={<RecipePage />} />
      <Route path=":id/edit" element={<EditRecipe />} />
    </Routes>
  )
}

function RecipeList() {
  const [recipes, setRecipes] = useState<Recipe[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listRecipes().then(setRecipes, (err: Error) => setError(err.message))
  }, [])

  return (
    <>
      <div className="title-row">
        <div>
          <h1>Recipes</h1>
          <p className="subtitle">Yummmmmmm</p>
        </div>
        <Link to="/recipes/new" className="btn btn-primary">New recipe</Link>
      </div>
      {error && <p role="alert">{error}</p>}
      {recipes && recipes.length === 0 && <p className="empty">No recipes yet.</p>}
      {recipes && recipes.length > 0 && (
        <div className="card-grid">
          {recipes.map((recipe) => (
            <Link key={recipe.id} to={`/recipes/${recipe.id}`} className="card card-link">
              <h2>{recipe.title}</h2>
              <p>{recipe.ingredients.length} ingredient{recipe.ingredients.length === 1 ? '' : 's'}</p>
            </Link>
          ))}
        </div>
      )}
    </>
  )
}

function NewRecipe() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const save = async (draft: RecipeDraft) => {
    setBusy(true)
    try {
      const id = await createRecipe(draft)
      navigate(`/recipes/${id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <>
      <p className="crumb"><Link to="/recipes">Recipes</Link></p>
      <h1>New recipe</h1>
      <p className="subtitle">Write it down before it's forgotten.</p>
      {error && <p role="alert">{error}</p>}
      <div className="card">
        <RecipeForm onSubmit={save} busy={busy} />
      </div>
    </>
  )
}

function EditRecipe() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getRecipe(id).then(setRecipe, (err: Error) => setError(err.message))
  }, [id])

  const save = async (draft: RecipeDraft) => {
    setBusy(true)
    try {
      await updateRecipe(id, draft)
      navigate(`/recipes/${id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <>
      <p className="crumb"><Link to={`/recipes/${id}`}>{recipe?.title ?? 'Recipe'}</Link></p>
      <h1>Edit recipe</h1>
      {error && <p role="alert">{error}</p>}
      {recipe && (
        <div className="card">
          <RecipeForm initial={recipe} onSubmit={save} busy={busy} />
        </div>
      )}
    </>
  )
}
