/**
 * The backend's recipe text follows a loose "### Title\n\n**Ingredients:**\n...\n\n
 * **Instructions:**\n..." convention (see src/rag/pipeline.py's SYSTEM_PROMPT and
 * recipe_loader.py's _format_recipe_text), but it's LLM-generated in some code paths,
 * so it's not guaranteed to match exactly (seen variants like "**Ingredients**" with
 * no colon, and "**Instructions and Tips**"). Every field is optional on purpose —
 * callers must handle a fully-unparsed result (fall back to showing raw text) rather
 * than assume parsing always succeeds.
 */
export interface ParsedRecipe {
  title: string | null;
  ingredients: string | null;
  instructions: string | null;
}

export function parseRecipeText(text: string): ParsedRecipe {
  const titleMatch = text.match(/^###\s*(.+)$/m);
  const title = titleMatch ? titleMatch[1].trim() : null;

  const ingredientsMatch = text.match(
    /\*\*Ingredients:?\*\*\s*([\s\S]*?)(?=\*\*Instructions|\n###|$)/i
  );
  const ingredients = ingredientsMatch ? ingredientsMatch[1].trim() : null;

  const instructionsMatch = text.match(/\*\*Instructions(?: and Tips)?:?\*\*\s*([\s\S]*?)(?=\n###|$)/i);
  const instructions = instructionsMatch ? instructionsMatch[1].trim() : null;

  return { title, ingredients, instructions };
}

/** Splits a multi-recipe blob ("### Recipe One\n...\n\n### Recipe Two\n...") into
 * individual recipe text blocks. Used when a single string field (e.g. QueryResponse's
 * "answer") might contain more than one "### Title" section. */
export function splitRecipeBlocks(text: string): string[] {
  const blocks = text.split(/(?=^###\s)/m).map((block) => block.trim()).filter(Boolean);
  return blocks.length > 0 ? blocks : [text];
}
