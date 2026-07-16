/**
 * UI text translations (EN/NO). Recipe/Ask content itself is translated server-side
 * (see src/rag/translator.py -- a dedicated NMT model, not an LLM: the fine-tuned
 * recipe model ignores a Norwegian instruction outright, and a general-purpose chat
 * model fabricates incorrect Norwegian vocabulary even translating a verified real
 * recipe) -- the backend just returns already-Norwegian text when language="no" is
 * requested, so this file only needs to cover the app's OWN chrome (buttons, headers,
 * labels, validation/error messages) plus the two RecipeCard section labels below,
 * which the backend's translated text doesn't include (see parseRecipeText.ts).
 */
import type { Language } from "./language";

export const translations = {
  en: {
    tabDeals: "Deals",
    tabCart: "Cart",
    tabAsk: "Ask",
    tabIngredients: "Ingredients",
    dealDetailTitle: "Recipe",

    addToCart: "Add to cart",
    cartEmpty: "Your cart is empty. Add items from Deals to get started.",
    useForMealIdeas: "Use for meal ideas",
    notUsedForMealIdeas: "Not used for meal suggestions",
    ingredientsSelectedForMealIdeas: (count: number) =>
      `${count} ingredient${count === 1 ? "" : "s"} selected for meal ideas`,
    offerMayBeExpired: "Offer may have expired",
    clearCart: "Clear cart",
    clearCartConfirmTitle: "Clear cart?",
    clearCartConfirmMessage: "This will remove all items from your cart.",
    cancel: "Cancel",

    foodTab: "Food",
    nonFoodTab: "Non-food",
    snacksSection: "Snacks",
    storesEmptyFood: "No items found right now — check back later.",
    storesEmptyNonFood: "No non-food items found right now — check back later.",
    storesUpdatedAt: (date: string, time: string) => `Updated ${date} ${time}`,
    storeCardItemsWithDiscount: (itemCount: number, discountCount: number) =>
      `${itemCount} items · ${discountCount} on sale`,
    storeCardItems: (itemCount: number) => `${itemCount} items`,

    askHeading: "Ask for a recipe",
    askPlaceholder: "e.g. norwegian ribbe, jollof rice, biryani...",
    askButton: "Ask",
    askBasedOn: (titles: string) => `Based on: ${titles}`,
    askNoExactMatch: "No exact match found — best-effort answer below.",

    ingredientsHeading: "What can I cook?",
    ingredientsSubheading: "Enter ingredients, separated by commas",
    ingredientsPlaceholder: "e.g. chicken, tomatoes, onions, rice",
    ingredientsButton: "Find recipes",
    ingredientsFoundCorpus: (count: number) => `Found ${count} matching recipe${count === 1 ? "" : "s"}`,
    ingredientsFoundGenerated: (count: number) => `No exact match — ${count} generated suggestion${count === 1 ? "" : "s"}`,
    showMore: "Show more",

    dealDetailRecipesWith: (productName: string) => `Recipes with ${productName}`,
    dealDetailEmpty: "No recipes found for this item.",

    recipeIngredientsLabel: "Ingredients",
    recipeInstructionsLabel: "Instructions",

    errorNetwork: "Can't reach the server. Check your internet connection and try again.",
    errorTimeout: "That took too long to respond. Please try again.",
    errorHttp: (statusCode: string | number) => `Server error (${statusCode}). Please try again later.`,
    errorInvalidResponse: "Got an unexpected response from the server. Please try again.",
    errorBackendFallback: "Something went wrong generating a response.",
    errorGeneric: "Something went wrong.",

    validationEnterQuestion: "Please enter a question.",
    validationQuestionTooLong: (max: number) => `Question is too long (max ${max} characters).`,
    validationEnterIngredient: "Please enter at least one ingredient.",
    validationTooManyIngredients: (max: number) => `Too many ingredients (max ${max}).`,
    validationIngredientTooLong: (item: string, max: number) => `"${item}" is too long (max ${max} characters).`,
  },
  no: {
    tabDeals: "Tilbud",
    tabCart: "Handlekurv",
    tabAsk: "Spør",
    tabIngredients: "Ingredienser",
    dealDetailTitle: "Oppskrift",

    addToCart: "Legg i handlekurv",
    cartEmpty: "Handlekurven din er tom. Legg til varer fra Tilbud for å komme i gang.",
    useForMealIdeas: "Bruk til middagsidéer",
    notUsedForMealIdeas: "Brukes ikke til middagsforslag",
    ingredientsSelectedForMealIdeas: (count: number) =>
      `${count} ingrediens${count === 1 ? "" : "er"} valgt til middagsidéer`,
    offerMayBeExpired: "Tilbudet kan ha utløpt",
    clearCart: "Tøm handlekurv",
    clearCartConfirmTitle: "Tømme handlekurven?",
    clearCartConfirmMessage: "Dette fjerner alle varer fra handlekurven din.",
    cancel: "Avbryt",

    foodTab: "Mat",
    nonFoodTab: "Ikke-mat",
    snacksSection: "Snacks",
    storesEmptyFood: "Ingen varer funnet akkurat nå — sjekk igjen senere.",
    storesEmptyNonFood: "Ingen ikke-mat-varer funnet akkurat nå — sjekk igjen senere.",
    storesUpdatedAt: (date: string, time: string) => `Oppdatert ${date} ${time}`,
    storeCardItemsWithDiscount: (itemCount: number, discountCount: number) =>
      `${itemCount} varer · ${discountCount} på tilbud`,
    storeCardItems: (itemCount: number) => `${itemCount} varer`,

    askHeading: "Spør om en oppskrift",
    askPlaceholder: "f.eks. ribbe, jollof rice, biryani...",
    askButton: "Spør",
    askBasedOn: (titles: string) => `Basert på: ${titles}`,
    askNoExactMatch: "Ingen eksakt treff funnet — beste forsøk på svar under.",

    ingredientsHeading: "Hva kan jeg lage?",
    ingredientsSubheading: "Skriv inn ingredienser, adskilt med komma",
    ingredientsPlaceholder: "f.eks. kylling, tomater, løk, ris",
    ingredientsButton: "Finn oppskrifter",
    ingredientsFoundCorpus: (count: number) => `Fant ${count} passende oppskrift${count === 1 ? "" : "er"}`,
    ingredientsFoundGenerated: (count: number) => `Ingen eksakt treff — ${count} genererte forslag`,
    showMore: "Vis mer",

    dealDetailRecipesWith: (productName: string) => `Oppskrifter med ${productName}`,
    dealDetailEmpty: "Ingen oppskrifter funnet for denne varen.",

    recipeIngredientsLabel: "Ingredienser",
    recipeInstructionsLabel: "Instruksjoner",

    errorNetwork: "Får ikke kontakt med serveren. Sjekk internettforbindelsen og prøv igjen.",
    errorTimeout: "Det tok for lang tid å svare. Prøv igjen.",
    errorHttp: (statusCode: string | number) => `Serverfeil (${statusCode}). Prøv igjen senere.`,
    errorInvalidResponse: "Fikk et uventet svar fra serveren. Prøv igjen.",
    errorBackendFallback: "Noe gikk galt under generering av svar.",
    errorGeneric: "Noe gikk galt.",

    validationEnterQuestion: "Skriv inn et spørsmål.",
    validationQuestionTooLong: (max: number) => `Spørsmålet er for langt (maks ${max} tegn).`,
    validationEnterIngredient: "Skriv inn minst én ingrediens.",
    validationTooManyIngredients: (max: number) => `For mange ingredienser (maks ${max}).`,
    validationIngredientTooLong: (item: string, max: number) => `«${item}» er for lang (maks ${max} tegn).`,
  },
} satisfies Record<Language, Record<string, unknown>>;

export type TranslationKey = keyof typeof translations.en;
