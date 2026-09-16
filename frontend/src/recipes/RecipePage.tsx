import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { getRecipe, removeRecipe, type Recipe } from './api'

function count(n: number, noun: string) {
  return `${n} ${noun}${n === 1 ? '' : 's'}`
}

export default function RecipePage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getRecipe(id).then(setRecipe, (err: Error) => setError(err.message))
  }, [id])

  const remove = async () => {
    if (!recipe || !confirm(`Delete "${recipe.title}"?`)) return
    try {
      await removeRecipe(recipe.id)
      navigate('/recipes')
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (error) return <p role="alert">{error}</p>
  if (!recipe) return null

  return (
    <>
      <p className="crumb"><Link to="/recipes">Recipes</Link></p>
      <h1>{recipe.title}</h1>
      <p className="subtitle">
        {count(recipe.ingredients.length, 'ingredient')} · {count(recipe.instructions.length, 'step')}
      </p>
      <div className="card recipe">
        <h2 className="rule-label" id="ingredients">ingredients</h2>
        <ul aria-labelledby="ingredients">
          {recipe.ingredients.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
        <h2 className="rule-label" id="method">method</h2>
        <ol aria-labelledby="method">
          {recipe.instructions.map((step, i) => <li key={i}>{step}</li>)}
        </ol>
      </div>
      <div className="actions">
        <Link to={`/recipes/${recipe.id}/edit`} className="btn">Edit</Link>
        <button type="button" className="btn btn-danger" onClick={remove}>Delete</button>
      </div>
    </>
  )
}
